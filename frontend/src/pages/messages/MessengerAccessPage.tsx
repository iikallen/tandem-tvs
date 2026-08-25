import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  api,
  cursorFromUrl,
  type CursorPage,
  type MediaAsset,
  type MessengerConversation,
  type MessengerMessage,
  type MessengerMessagePage,
  type MessengerPerson,
} from "../../shared/api";
import { t } from "../../shared/i18n";
import { Avatar } from "../../shared/ui/Avatar";
import { CloseIcon, SearchIcon } from "../../shared/ui/icons";
import { PageState } from "../../shared/ui/PageState";

type PendingMessage = {
  conversationId: string;
  clientMessageId: string;
  body: string;
  replyToId?: string;
  attachmentIds?: string[];
  forwardMessageId?: string;
  state: "sending" | "failed";
};

type NewConversationMode = "direct" | "group" | "channel";

const REACTIONS = [
  ["LIKE", "👍"],
  ["LOVE", "❤️"],
  ["LAUGH", "😂"],
  ["WOW", "😮"],
  ["SAD", "😢"],
] as const;

function conversationTitle(
  conversation: MessengerConversation,
  currentUserId: number,
): string {
  if (conversation.type !== "DIRECT") return conversation.title;
  return (
    conversation.peer?.full_name ??
    conversation.members?.find(
      (membership) => membership.user.id !== currentUserId,
    )?.user.full_name ??
    t("messengerUnknownPerson")
  );
}

function conversationSubtitle(
  conversation: MessengerConversation,
  currentUserId: number,
): string {
  if (conversation.last_message) {
    const preview = conversation.last_message;
    const authorId =
      "author_id" in preview ? preview.author_id : preview.author.id;
    const authorName =
      "author_name" in preview ? preview.author_name : preview.author.full_name;
    const body =
      "body_preview" in preview ? preview.body_preview : preview.body;
    const prefix =
      authorId === currentUserId ? t("messengerYou") : authorName.split(" ")[0];
    return `${prefix}: ${body}`;
  }
  return conversation.type !== "DIRECT"
    ? t("messengerMemberCount", {
        count: conversation.member_count ?? conversation.members?.length ?? 0,
      })
    : t("messengerNoMessages");
}

function shortTime(value: string | null): string {
  if (!value) return "";
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function receiptLabel(message: MessengerMessage): string {
  if (message.receipt.read !== undefined) {
    if (message.receipt.read) return t("messengerRead");
    return message.receipt.delivered
      ? t("messengerDelivered")
      : t("messengerSent");
  }
  return t("messengerReceiptCount", {
    delivered: message.receipt.delivered_count ?? 0,
    count: message.receipt.read_count,
    total: message.receipt.recipient_count,
  });
}

function NewConversationDialog({
  mode,
  onClose,
  onCreated,
}: {
  mode: NewConversationMode;
  onClose: () => void;
  onCreated: (conversation: MessengerConversation) => void;
}) {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [title, setTitle] = useState("");
  const [members, setMembers] = useState<number[]>([]);
  const [writers, setWriters] = useState<number[]>([]);
  const [discussionEnabled, setDiscussionEnabled] = useState(false);
  const searchInput = useRef<HTMLInputElement>(null);
  const people = useQuery({
    queryKey: ["messenger-people", debouncedSearch],
    queryFn: () => api.messengerPeople(debouncedSearch),
  });
  const create = useMutation({
    mutationFn: (person?: MessengerPerson) =>
      mode === "direct" && person
        ? api.createDirectConversation(person.id)
        : mode === "channel"
          ? api.createChannelConversation(
              title,
              members,
              writers,
              discussionEnabled,
            )
          : api.createGroupConversation(title, members),
    onSuccess: onCreated,
  });

  useEffect(() => {
    const timer = window.setTimeout(
      () => setDebouncedSearch(search.trim()),
      300,
    );
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    searchInput.current?.focus();
    return () => previousFocus?.focus();
  }, []);

  function submitGroup(event: FormEvent) {
    event.preventDefault();
    if (title.trim() && members.length) create.mutate(undefined);
  }

  function handleDialogKey(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled])",
      ),
    );
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }

  return (
    <div className="dialog-scrim" role="presentation" onMouseDown={onClose}>
      <section
        className="messenger-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="messenger-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
        onKeyDown={handleDialogKey}
      >
        <header className="messenger-dialog__header">
          <div>
            <p className="overline">{t("messenger")}</p>
            <h2 id="messenger-dialog-title">
              {mode === "direct"
                ? t("messengerStartDirect")
                : mode === "channel"
                  ? t("messengerStartChannel")
                  : t("messengerStartGroup")}
            </h2>
          </div>
          <button
            className="messenger-icon-button"
            type="button"
            onClick={onClose}
            aria-label={t("close")}
          >
            <CloseIcon />
          </button>
        </header>
        {mode !== "direct" && (
          <label className="messenger-field">
            <span>{t("messengerGroupTitle")}</span>
            <input
              value={title}
              maxLength={255}
              onChange={(event) => setTitle(event.target.value)}
              autoFocus
            />
          </label>
        )}
        <label className="messenger-search">
          <SearchIcon aria-hidden="true" />
          <span className="sr-only">{t("messengerSearchPeople")}</span>
          <input
            ref={searchInput}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t("messengerSearchPeople")}
          />
        </label>
        <div className="messenger-people" aria-live="polite">
          {people.isPending && <p>{t("loadingMore")}</p>}
          {people.isError && <p role="alert">{t("errorDescription")}</p>}
          {people.data?.map((person) => (
            <label className="messenger-person" key={person.id}>
              {mode !== "direct" && (
                <input
                  type="checkbox"
                  checked={members.includes(person.id)}
                  onChange={() => {
                    const removing = members.includes(person.id);
                    setMembers((current) =>
                      removing
                        ? current.filter((id) => id !== person.id)
                        : [...current, person.id],
                    );
                    if (removing)
                      setWriters((current) =>
                        current.filter((id) => id !== person.id),
                      );
                  }}
                />
              )}
              <Avatar name={person.full_name} imageUrl={person.avatar_url} />
              <span>
                <strong>{person.full_name}</strong>
                <small>
                  {person.job_title ||
                    person.org_unit_name ||
                    t("notSpecified")}
                </small>
              </span>
              {mode === "direct" && (
                <button
                  className="button button--secondary"
                  type="button"
                  disabled={create.isPending}
                  onClick={() => create.mutate(person)}
                >
                  {t("messengerOpenChat")}
                </button>
              )}
              {mode === "channel" && members.includes(person.id) && (
                <button
                  className="button button--secondary"
                  type="button"
                  aria-pressed={writers.includes(person.id)}
                  onClick={() =>
                    setWriters((current) =>
                      current.includes(person.id)
                        ? current.filter((id) => id !== person.id)
                        : [...current, person.id],
                    )
                  }
                >
                  {writers.includes(person.id)
                    ? t("messengerChannelWriter")
                    : t("messengerChannelMember")}
                </button>
              )}
            </label>
          ))}
          {!people.isPending && people.data?.length === 0 && (
            <p>{t("messengerPeopleEmpty")}</p>
          )}
        </div>
        {create.isError && <p role="alert">{t("messengerCreateFailed")}</p>}
        {mode === "channel" && (
          <label className="check-row">
            <input
              type="checkbox"
              checked={discussionEnabled}
              onChange={(event) => setDiscussionEnabled(event.target.checked)}
            />
            <span>{t("messengerChannelDiscussion")}</span>
          </label>
        )}
        {mode !== "direct" && (
          <form className="messenger-dialog__actions" onSubmit={submitGroup}>
            <span>
              {t("messengerSelectedCount", { count: members.length })}
            </span>
            <button
              className="button"
              type="submit"
              disabled={!title.trim() || !members.length || create.isPending}
            >
              {mode === "channel"
                ? t("messengerCreateChannel")
                : t("messengerCreateGroup")}
            </button>
          </form>
        )}
      </section>
    </div>
  );
}

export function MessengerAccessPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const targetMessageId = searchParams.get("message");
  const [selectedId, setSelectedId] = useState<string | null>(
    searchParams.get("conversation"),
  );
  const [dialog, setDialog] = useState<NewConversationMode | null>(null);
  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState<MessengerMessage | null>(null);
  const [editing, setEditing] = useState<MessengerMessage | null>(null);
  const [forwarding, setForwarding] = useState<MessengerMessage | null>(null);
  const [attachments, setAttachments] = useState<MediaAsset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [composerError, setComposerError] = useState(false);
  const [search, setSearch] = useState("");
  const [showMembers, setShowMembers] = useState(false);
  const [memberCandidate, setMemberCandidate] = useState(0);
  const [typingUsers, setTypingUsers] = useState<Record<number, number>>({});
  const [onlineUsers, setOnlineUsers] = useState<Record<number, number>>({});
  const [pending, setPending] = useState<PendingMessage[]>([]);
  const [realtime, setRealtime] = useState<
    "connecting" | "connected" | "stopped"
  >("connecting");
  const messageEnd = useRef<HTMLDivElement>(null);
  const socketRef = useRef<WebSocket | undefined>(undefined);
  const seenEvents = useRef(new Set<string>());
  const receiptRefreshTimers = useRef(new Map<string, number>());
  const typingStop = useRef<number>(0);
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const conversations = useQuery({
    queryKey: ["messenger-conversations"],
    queryFn: () => api.messengerConversations(),
  });
  const selected = conversations.data?.results.find(
    (conversation) => conversation.id === selectedId,
  );
  const detail = useQuery({
    queryKey: ["messenger-conversation", selectedId],
    queryFn: () => api.messengerConversation(selectedId ?? ""),
    enabled: Boolean(selectedId),
  });
  const members = useQuery({
    queryKey: ["messenger-members", selectedId],
    queryFn: () => api.messengerMembers(selectedId ?? ""),
    enabled: Boolean(selectedId),
  });
  const memberCandidates = useQuery({
    queryKey: ["messenger-people", ""],
    queryFn: () => api.messengerPeople(),
    enabled: showMembers,
  });
  const messages = useQuery({
    queryKey: ["messenger-messages", selectedId, targetMessageId],
    queryFn: () =>
      targetMessageId
        ? api.messengerMessageContext(selectedId ?? "", targetMessageId)
        : api.messengerMessages(selectedId ?? ""),
    enabled: Boolean(selectedId),
  });

  useEffect(() => {
    if (!targetMessageId || !messages.data) return;
    document
      .getElementById(`message-${targetMessageId}`)
      ?.scrollIntoView({ block: "center" });
  }, [messages.data, targetMessageId]);
  const searchResults = useQuery({
    queryKey: ["messenger-search", selectedId, search],
    queryFn: () => api.searchMessengerMessages(selectedId ?? "", search),
    enabled: Boolean(selectedId && search.trim()),
  });
  const currentPending = pending.filter(
    (message) =>
      message.conversationId === selectedId &&
      !messages.data?.messages.some(
        (saved) => saved.client_message_id === message.clientMessageId,
      ),
  );

  useEffect(() => {
    let stopped = false;
    let socket: WebSocket | undefined;
    let reconnectTimer = 0;
    let reconnectDelay = 1_000;
    const refreshTimers = receiptRefreshTimers.current;

    function reconnect() {
      reconnectTimer = window.setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 15_000);
    }

    async function connect() {
      setRealtime("connecting");
      try {
        const { ticket } = await api.messengerRealtimeTicket();
        if (stopped) return;
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(
          `${protocol}//${window.location.host}/ws/v1/messenger?ticket=${encodeURIComponent(ticket)}`,
        );
        socketRef.current = socket;
        socket.onopen = () => {
          reconnectDelay = 1_000;
          setRealtime("connected");
        };
        socket.onmessage = (event) => {
          let hint: {
            event_id?: string;
            type?: string;
            conversation_id?: string;
            user_id?: number;
            online?: boolean;
            sequence?: number;
            message_id?: string;
          };
          try {
            hint = JSON.parse(String(event.data)) as typeof hint;
          } catch {
            return;
          }
          if (!hint.type?.startsWith("messenger.")) return;
          if (hint.event_id) {
            if (seenEvents.current.has(hint.event_id)) return;
            seenEvents.current.add(hint.event_id);
            if (seenEvents.current.size > 1_000) {
              const oldest = seenEvents.current.values().next().value;
              if (oldest) seenEvents.current.delete(oldest);
            }
          }
          if (hint.user_id && hint.type === "messenger.presence.changed") {
            setOnlineUsers((current) => {
              const next = { ...current };
              if (hint.online) next[hint.user_id!] = Date.now() + 70_000;
              else delete next[hint.user_id!];
              return next;
            });
            return;
          }
          if (hint.user_id && hint.type.startsWith("messenger.typing.")) {
            setTypingUsers((current) => {
              const next = { ...current };
              if (hint.type === "messenger.typing.started") {
                next[hint.user_id!] = Date.now() + 5_000;
              } else delete next[hint.user_id!];
              return next;
            });
            return;
          }
          if (
            hint.conversation_id &&
            (hint.type === "messenger.read.changed" ||
              hint.type === "messenger.delivered.changed")
          ) {
            const existing = refreshTimers.get(hint.conversation_id);
            if (existing) window.clearTimeout(existing);
            refreshTimers.set(
              hint.conversation_id,
              window.setTimeout(() => {
                refreshTimers.delete(hint.conversation_id!);
                void queryClient.invalidateQueries({
                  queryKey: ["messenger-messages", hint.conversation_id],
                });
                void queryClient.invalidateQueries({
                  queryKey: ["messenger-conversations"],
                });
              }, 250),
            );
            return;
          }
          if (
            hint.conversation_id &&
            hint.message_id &&
            hint.type === "messenger.message.created"
          ) {
            void api
              .messengerMessage(hint.message_id)
              .then((message) => {
                queryClient.setQueriesData<MessengerMessagePage>(
                  {
                    queryKey: ["messenger-messages", hint.conversation_id],
                  },
                  (current) =>
                    current &&
                    !current.messages.some((row) => row.id === message.id)
                      ? {
                          ...current,
                          messages: [...current.messages, message],
                        }
                      : current,
                );
              })
              .catch(() =>
                queryClient.invalidateQueries({
                  queryKey: ["messenger-messages", hint.conversation_id],
                }),
              );
          } else if (
            hint.conversation_id &&
            (hint.type.startsWith("messenger.message.") ||
              hint.type === "messenger.reaction.changed")
          ) {
            void queryClient.invalidateQueries({
              queryKey: ["messenger-messages", hint.conversation_id],
            });
          }
          void queryClient.invalidateQueries({
            queryKey: ["messenger-conversations"],
          });
          if (
            hint.conversation_id &&
            hint.type.startsWith("messenger.membership.")
          ) {
            void queryClient.invalidateQueries({
              queryKey: ["messenger-members", hint.conversation_id],
            });
          }
          if (
            hint.conversation_id &&
            (hint.type === "messenger.message.pinned" ||
              hint.type === "messenger.message.unpinned")
          ) {
            void queryClient.invalidateQueries({
              queryKey: ["messenger-conversation", hint.conversation_id],
            });
          }
        };
        socket.onclose = (event) => {
          if (stopped) return;
          if (event.code === 4403) {
            setRealtime("stopped");
            void queryClient.invalidateQueries({ queryKey: ["session"] });
            void queryClient.invalidateQueries({ queryKey: ["me"] });
            return;
          }
          setRealtime("connecting");
          reconnect();
        };
      } catch {
        if (!stopped) reconnect();
      }
    }

    void connect();
    return () => {
      stopped = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
      socketRef.current = undefined;
      for (const timer of refreshTimers.values()) {
        window.clearTimeout(timer);
      }
      refreshTimers.clear();
    };
  }, [queryClient]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const now = Date.now();
      setTypingUsers((current) =>
        Object.fromEntries(
          Object.entries(current).filter(([, until]) => until > now),
        ),
      );
      setOnlineUsers((current) =>
        Object.fromEntries(
          Object.entries(current).filter(([, until]) => until > now),
        ),
      );
    }, 1_000);
    return () => window.clearInterval(timer);
  }, []);

  const newestSequence = messages.data?.messages.at(-1)?.sequence ?? 0;
  useEffect(() => {
    if (!selectedId || newestSequence < 1) return;
    void api
      .markMessengerDelivered(selectedId, newestSequence)
      .catch(() => undefined);
  }, [newestSequence, selectedId]);

  useEffect(() => {
    if (!selectedId || !selected?.unread_count || newestSequence < 1) return;
    let active = true;
    void api
      .markMessengerRead(selectedId, newestSequence)
      .then(() => {
        if (!active) return;
        queryClient.setQueryData<CursorPage<MessengerConversation>>(
          ["messenger-conversations"],
          (current) =>
            current && {
              ...current,
              results: current.results.map((conversation) =>
                conversation.id === selectedId
                  ? { ...conversation, unread_count: 0 }
                  : conversation,
              ),
            },
        );
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [newestSequence, queryClient, selected?.unread_count, selectedId]);

  useEffect(() => {
    messageEnd.current?.scrollIntoView?.({ block: "end" });
  }, [messages.data?.messages.length, currentPending.length]);

  useEffect(() => {
    if (!selectedId || editing || draft === (selected?.state?.draft_body ?? ""))
      return;
    const timer = window.setTimeout(() => {
      void api.updateMessengerState(selectedId, { draft_body: draft });
    }, 700);
    return () => window.clearTimeout(timer);
  }, [draft, editing, selected?.state?.draft_body, selectedId]);

  const send = useMutation({
    mutationFn: (message: PendingMessage) =>
      api.sendMessengerMessage(
        message.conversationId,
        message.clientMessageId,
        message.body,
        {
          reply_to_id: message.replyToId,
          attachment_ids: message.attachmentIds,
          forward_message_id: message.forwardMessageId,
          kind:
            selected?.type === "CHANNEL"
              ? ["ADMIN", "WRITER"].includes(myMembership?.role ?? "")
                ? "CHANNEL_POST"
                : "DISCUSSION"
              : "CHAT",
        },
      ),
    onSuccess: (saved, optimistic) => {
      queryClient.setQueryData<MessengerMessagePage>(
        ["messenger-messages", optimistic.conversationId, targetMessageId],
        (current) =>
          current
            ? {
                ...current,
                messages: [
                  ...current.messages.filter(
                    (message) =>
                      message.client_message_id !== saved.client_message_id,
                  ),
                  saved,
                ],
              }
            : current,
      );
      setPending((current) =>
        current.filter(
          (message) => message.clientMessageId !== optimistic.clientMessageId,
        ),
      );
      void queryClient.invalidateQueries({
        queryKey: ["messenger-conversations"],
      });
      void api.updateMessengerState(optimistic.conversationId, {
        draft_body: "",
      });
    },
    onError: (_error, optimistic) => {
      setPending((current) =>
        current.map((message) =>
          message.clientMessageId === optimistic.clientMessageId
            ? { ...message, state: "failed" }
            : message,
        ),
      );
    },
  });

  async function submitMessage(event: FormEvent) {
    event.preventDefault();
    const body = draft.trim();
    if (!selectedId || (!body && !attachments.length && !forwarding)) return;
    if (editing) {
      if (!body) return;
      setComposerError(false);
      try {
        await api.editMessengerMessage(editing.id, body);
        setEditing(null);
        setDraft("");
        await queryClient.invalidateQueries({
          queryKey: ["messenger-messages", selectedId],
        });
      } catch {
        setComposerError(true);
      }
      return;
    }
    const optimistic: PendingMessage = {
      conversationId: selectedId,
      clientMessageId: crypto.randomUUID(),
      body,
      replyToId: replyTo?.id,
      attachmentIds: attachments.map((asset) => asset.id),
      forwardMessageId: forwarding?.id,
      state: "sending",
    };
    setDraft("");
    setReplyTo(null);
    setForwarding(null);
    setAttachments([]);
    setPending((current) => [...current, optimistic]);
    send.mutate(optimistic);
  }

  function handleComposerKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  function announceTyping(value: string) {
    setDraft(value);
    const socket = socketRef.current;
    if (
      !selectedId ||
      socket?.readyState !== WebSocket.OPEN ||
      typeof socket.send !== "function"
    )
      return;
    socket.send(
      JSON.stringify({
        type: "typing",
        conversation_id: selectedId,
        is_typing: true,
      }),
    );
    window.clearTimeout(typingStop.current);
    typingStop.current = window.setTimeout(() => {
      if (typeof socketRef.current?.send !== "function") return;
      socketRef.current.send(
        JSON.stringify({
          type: "typing",
          conversation_id: selectedId,
          is_typing: false,
        }),
      );
    }, 1_500);
  }

  async function uploadAttachment(file: File | undefined) {
    if (!file || !selectedId) return;
    setUploading(true);
    setComposerError(false);
    try {
      const asset = await api.uploadMessengerAttachment(selectedId, file);
      setAttachments((current) => [...current, asset]);
    } catch {
      setComposerError(true);
    } finally {
      setUploading(false);
    }
  }

  function selectConversation(conversation: MessengerConversation) {
    setSelectedId(conversation.id);
    setDraft(conversation.state?.draft_body ?? "");
    setReplyTo(null);
    setEditing(null);
    setAttachments([]);
  }

  const selectedTitle = useMemo(
    () => (selected && me.data ? conversationTitle(selected, me.data.id) : ""),
    [me.data, selected],
  );
  const myMembership = members.data?.results.find(
    (membership) => membership.user.id === me.data?.id,
  );
  const canPinMessage =
    selected?.type === "DIRECT" || myMembership?.role === "ADMIN";

  if (me.isPending || conversations.isPending)
    return <PageState kind="loading" />;
  if (me.isError || conversations.isError)
    return <PageState error={me.error ?? conversations.error} />;

  return (
    <section className={`messenger${selected ? " messenger--selected" : ""}`}>
      <aside
        className="messenger-inbox"
        aria-label={t("messengerConversationList")}
      >
        <header className="messenger-inbox__header">
          <div>
            <p className="overline">{t("workspace")}</p>
            <h1>{t("messages")}</h1>
          </div>
          <span
            className={`messenger-status messenger-status--${realtime}`}
            title={
              realtime === "connected"
                ? t("realtimeConnected")
                : realtime === "connecting"
                  ? t("realtimeReconnecting")
                  : t("realtimeStopped")
            }
          >
            <span aria-hidden="true" />
            <span className="sr-only">
              {realtime === "connected"
                ? t("realtimeConnected")
                : realtime === "connecting"
                  ? t("realtimeReconnecting")
                  : t("realtimeStopped")}
            </span>
          </span>
        </header>
        <div className="messenger-new-actions">
          <button
            className="button"
            type="button"
            onClick={() => setDialog("direct")}
          >
            {t("messengerNewDirect")}
          </button>
          <button
            className="button button--secondary"
            type="button"
            onClick={() => setDialog("group")}
          >
            {t("messengerNewGroup")}
          </button>
          {me.data?.access.messenger.includes("ADMIN") && (
            <button
              className="button button--secondary"
              type="button"
              onClick={() => setDialog("channel")}
            >
              {t("messengerNewChannel")}
            </button>
          )}
        </div>
        <div className="messenger-conversations">
          {conversations.data?.results.map((conversation) => {
            const title = conversationTitle(conversation, me.data.id);
            const peer =
              conversation.peer ??
              conversation.members?.find(
                (membership) => membership.user.id !== me.data.id,
              )?.user;
            return (
              <button
                key={conversation.id}
                className={`messenger-conversation${conversation.id === selectedId ? " is-active" : ""}`}
                type="button"
                onClick={() => selectConversation(conversation)}
                aria-current={
                  conversation.id === selectedId ? "page" : undefined
                }
              >
                <Avatar name={title} imageUrl={peer?.avatar_url} />
                <span className="messenger-conversation__copy">
                  <strong>{title}</strong>
                  <small>
                    {conversationSubtitle(conversation, me.data.id)}
                  </small>
                </span>
                <span className="messenger-conversation__meta">
                  <time>{shortTime(conversation.last_message_at)}</time>
                  {conversation.unread_count > 0 && (
                    <span className="messenger-unread" aria-label={t("unread")}>
                      {conversation.unread_count}
                    </span>
                  )}
                </span>
              </button>
            );
          })}
          {conversations.data?.next && (
            <button
              className="messenger-load-older"
              type="button"
              onClick={async () => {
                const next = await api.messengerConversations(
                  cursorFromUrl(conversations.data?.next ?? null),
                );
                queryClient.setQueryData<CursorPage<MessengerConversation>>(
                  ["messenger-conversations"],
                  (current) =>
                    current
                      ? {
                          ...next,
                          previous: current.previous,
                          results: [...current.results, ...next.results],
                        }
                      : next,
                );
              }}
            >
              {t("loadingMore")}
            </button>
          )}
          {conversations.data?.results.length === 0 && (
            <div className="messenger-empty">
              <strong>{t("messengerEmpty")}</strong>
              <p>{t("messengerEmptyDescription")}</p>
            </div>
          )}
        </div>
      </aside>

      <article
        className="messenger-thread"
        aria-label={selectedTitle || t("messages")}
      >
        {selected && me.data ? (
          <>
            <header className="messenger-thread__header">
              <button
                className="messenger-back"
                type="button"
                onClick={() => setSelectedId(null)}
              >
                {t("messengerBack")}
              </button>
              <div>
                <h2>{selectedTitle}</h2>
                <p>
                  {selected.type === "GROUP"
                    ? t("messengerMemberCount", {
                        count:
                          selected.member_count ??
                          selected.members?.length ??
                          0,
                      })
                    : (
                        selected.peer ??
                        selected.members?.find(
                          (membership) => membership.user.id !== me.data.id,
                        )?.user
                      )?.job_title || t("messengerDirect")}
                  {selected.type === "DIRECT" &&
                    selected.peer &&
                    onlineUsers[selected.peer.id] &&
                    ` · ${t("messengerOnline")}`}
                </p>
              </div>
              <div className="messenger-thread__actions">
                {selected.type === "CHANNEL" &&
                  myMembership?.role === "ADMIN" && (
                    <button
                      type="button"
                      onClick={() =>
                        void api
                          .updateMessengerChannelSettings(
                            selected.id,
                            !selected.discussion_enabled,
                          )
                          .then(() => {
                            void queryClient.invalidateQueries({
                              queryKey: ["messenger-conversations"],
                            });
                            void detail.refetch();
                          })
                      }
                    >
                      {selected.discussion_enabled
                        ? t("messengerDisableDiscussion")
                        : t("messengerEnableDiscussion")}
                    </button>
                  )}
                <button
                  type="button"
                  onClick={() => setShowMembers((current) => !current)}
                >
                  {t("messengerMembers")}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    void api
                      .updateMessengerState(selected.id, {
                        pinned: !selected.state?.pinned_at,
                      })
                      .then(() =>
                        queryClient.invalidateQueries({
                          queryKey: ["messenger-conversations"],
                        }),
                      )
                  }
                >
                  {selected.state?.pinned_at
                    ? t("messengerUnpinChat")
                    : t("messengerPinChat")}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    void api
                      .updateMessengerState(selected.id, {
                        muted_until: selected.state?.muted_until
                          ? null
                          : new Date(Date.now() + 86_400_000).toISOString(),
                      })
                      .then(() =>
                        queryClient.invalidateQueries({
                          queryKey: ["messenger-conversations"],
                        }),
                      )
                  }
                >
                  {selected.state?.muted_until
                    ? t("messengerUnmute")
                    : t("messengerMute")}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    void api
                      .updateMessengerState(selected.id, {
                        is_archived: !selected.state?.is_archived,
                      })
                      .then(() =>
                        queryClient.invalidateQueries({
                          queryKey: ["messenger-conversations"],
                        }),
                      )
                  }
                >
                  {selected.state?.is_archived
                    ? t("messengerRestore")
                    : t("messengerArchive")}
                </button>
              </div>
            </header>
            <label className="messenger-thread-search">
              <SearchIcon aria-hidden="true" />
              <span className="sr-only">{t("messengerSearchMessages")}</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t("messengerSearchMessages")}
              />
            </label>
            {search.trim() && (
              <div className="messenger-search-results">
                {searchResults.data?.results.map((message) => (
                  <button
                    type="button"
                    key={message.id}
                    onClick={() => {
                      setSearch("");
                      navigate(
                        `/messages?conversation=${selected.id}&message=${message.id}`,
                      );
                    }}
                  >
                    <strong>{message.author.full_name}</strong>
                    <span>{message.body}</span>
                  </button>
                ))}
                {!searchResults.isPending &&
                  searchResults.data?.results.length === 0 && (
                    <p>{t("messengerSearchEmpty")}</p>
                  )}
              </div>
            )}
            {showMembers && (
              <section className="messenger-member-panel">
                <header>
                  <h3>{t("messengerMembers")}</h3>
                  {selected.type === "GROUP" && (
                    <button
                      type="button"
                      onClick={() =>
                        void api
                          .leaveMessengerConversation(selected.id)
                          .then(() => {
                            setSelectedId(null);
                            void queryClient.invalidateQueries({
                              queryKey: ["messenger-conversations"],
                            });
                          })
                      }
                    >
                      {t("messengerLeave")}
                    </button>
                  )}
                </header>
                {members.data?.results.map((membership) => (
                  <div
                    className="messenger-member-row"
                    key={membership.user.id}
                  >
                    <Avatar
                      name={membership.user.full_name}
                      imageUrl={membership.user.avatar_url}
                    />
                    <span>
                      <strong>{membership.user.full_name}</strong>
                      <small>{membership.role}</small>
                    </span>
                    {members.data.results.find(
                      (row) => row.user.id === me.data.id,
                    )?.role === "ADMIN" &&
                      membership.user.id !== me.data.id && (
                        <span>
                          <button
                            type="button"
                            onClick={() =>
                              void api
                                .changeMessengerMemberRole(
                                  selected.id,
                                  membership.user.id,
                                  membership.role === "ADMIN"
                                    ? "MEMBER"
                                    : "ADMIN",
                                )
                                .then(() => members.refetch())
                            }
                          >
                            {membership.role === "ADMIN"
                              ? t("messengerDemote")
                              : t("messengerPromote")}
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              void api
                                .removeMessengerMember(
                                  selected.id,
                                  membership.user.id,
                                )
                                .then(() => members.refetch())
                            }
                          >
                            {t("remove")}
                          </button>
                        </span>
                      )}
                  </div>
                ))}
                {selected.type === "GROUP" &&
                  members.data?.results.find(
                    (row) => row.user.id === me.data.id,
                  )?.role === "ADMIN" && (
                    <div className="messenger-member-add">
                      <select
                        value={memberCandidate}
                        onChange={(event) =>
                          setMemberCandidate(Number(event.target.value))
                        }
                      >
                        <option value={0}>{t("messengerAddMember")}</option>
                        {memberCandidates.data
                          ?.filter(
                            (person) =>
                              !members.data?.results.some(
                                (row) => row.user.id === person.id,
                              ),
                          )
                          .map((person) => (
                            <option key={person.id} value={person.id}>
                              {person.full_name}
                            </option>
                          ))}
                      </select>
                      <button
                        type="button"
                        disabled={!memberCandidate}
                        onClick={() =>
                          void api
                            .addMessengerMember(selected.id, memberCandidate)
                            .then(() => {
                              setMemberCandidate(0);
                              void members.refetch();
                            })
                        }
                      >
                        {t("add")}
                      </button>
                    </div>
                  )}
              </section>
            )}
            {detail.data?.pinned_messages?.map((message) => (
              <div className="messenger-pinned" key={message.id}>
                <strong>{t("messengerPinned")}</strong>
                <span>{message.body_preview}</span>
                <button
                  type="button"
                  onClick={() =>
                    void api
                      .unpinMessengerMessage(message.id)
                      .then(() => detail.refetch())
                  }
                >
                  {t("remove")}
                </button>
              </div>
            ))}
            <div className="messenger-history" aria-live="polite">
              {messages.isPending && <PageState kind="loading" />}
              {messages.isError && <PageState error={messages.error} />}
              {messages.data?.has_more && (
                <button
                  className="messenger-load-older"
                  type="button"
                  onClick={async () => {
                    const older = await api.messengerMessages(
                      selected.id,
                      messages.data?.next_before_sequence ?? undefined,
                    );
                    queryClient.setQueryData<MessengerMessagePage>(
                      ["messenger-messages", selected.id, targetMessageId],
                      (current) =>
                        current
                          ? {
                              messages: [
                                ...older.messages,
                                ...current.messages,
                              ],
                              has_more: older.has_more,
                              next_before_sequence: older.next_before_sequence,
                            }
                          : older,
                    );
                  }}
                >
                  {t("messengerLoadOlder")}
                </button>
              )}
              {messages.data?.messages.map((message) => {
                const mine = message.author.id === me.data.id;
                return (
                  <div
                    id={`message-${message.id}`}
                    className={`messenger-message${mine ? " messenger-message--mine" : ""}${message.id === targetMessageId ? " messenger-message--target" : ""}`}
                    key={message.id}
                  >
                    {!mine && <strong>{message.author.full_name}</strong>}
                    {message.reply_to && (
                      <button
                        className="messenger-quote"
                        type="button"
                        onClick={() => undefined}
                      >
                        <strong>{message.reply_to.author.full_name}</strong>
                        <span>
                          {message.reply_to.deleted_at
                            ? t("messengerDeleted")
                            : message.reply_to.body_preview}
                        </span>
                      </button>
                    )}
                    {message.forwarded_snapshot && (
                      <blockquote className="messenger-forward">
                        <strong>
                          {message.forwarded_snapshot.author_name}
                        </strong>
                        <p>{message.forwarded_snapshot.body}</p>
                      </blockquote>
                    )}
                    <p>
                      {message.deleted_at
                        ? t("messengerDeleted")
                        : message.body}
                    </p>
                    {message.attachments?.map((asset) => (
                      <a
                        className="messenger-attachment"
                        href={asset.content_url}
                        key={asset.id}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {asset.original_name} · {Math.ceil(asset.size / 1024)}{" "}
                        KB
                      </a>
                    ))}
                    {!message.deleted_at && (
                      <div className="messenger-reactions">
                        {REACTIONS.map(([kind, emoji]) => {
                          const reaction = message.reactions?.find(
                            (item) => item.reaction_type === kind,
                          );
                          return (
                            <button
                              type="button"
                              className={
                                reaction?.mine ? "is-active" : undefined
                              }
                              key={kind}
                              aria-label={`${kind}${reaction ? ` ${reaction.count}` : ""}`}
                              onClick={() =>
                                void (
                                  reaction?.mine
                                    ? api.deleteMessengerReaction(message.id)
                                    : api.putMessengerReaction(message.id, kind)
                                ).then(() =>
                                  queryClient.invalidateQueries({
                                    queryKey: [
                                      "messenger-messages",
                                      selected.id,
                                    ],
                                  }),
                                )
                              }
                            >
                              {emoji} {reaction?.count || ""}
                            </button>
                          );
                        })}
                      </div>
                    )}
                    <div className="messenger-message__actions">
                      {!message.deleted_at && (
                        <>
                          <button
                            type="button"
                            onClick={() => setReplyTo(message)}
                          >
                            {t("messengerReply")}
                          </button>
                          <button
                            type="button"
                            onClick={() => setForwarding(message)}
                          >
                            {t("messengerForward")}
                          </button>
                          {canPinMessage && (
                            <button
                              type="button"
                              onClick={() =>
                                void api
                                  .pinMessengerMessage(message.id)
                                  .then(() =>
                                    queryClient.invalidateQueries({
                                      queryKey: [
                                        "messenger-conversation",
                                        selected.id,
                                      ],
                                    }),
                                  )
                              }
                            >
                              {t("messengerPinMessage")}
                            </button>
                          )}
                        </>
                      )}
                      {mine && !message.deleted_at && (
                        <>
                          <button
                            type="button"
                            onClick={() => {
                              setEditing(message);
                              setDraft(message.body);
                            }}
                          >
                            {t("edit")}
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              void api
                                .deleteMessengerMessage(message.id)
                                .then(() =>
                                  queryClient.invalidateQueries({
                                    queryKey: [
                                      "messenger-messages",
                                      selected.id,
                                    ],
                                  }),
                                )
                            }
                          >
                            {t("remove")}
                          </button>
                        </>
                      )}
                    </div>
                    <span>
                      <time dateTime={message.created_at}>
                        {shortTime(message.created_at)}
                      </time>
                      {message.edited_at && (
                        <small>{t("messengerEdited")}</small>
                      )}
                      {mine && <small>{receiptLabel(message)}</small>}
                    </span>
                  </div>
                );
              })}
              {currentPending.map((message) => (
                <div
                  className="messenger-message messenger-message--mine messenger-message--pending"
                  key={message.clientMessageId}
                >
                  <p>{message.body}</p>
                  <span>
                    <small>
                      {message.state === "sending"
                        ? t("messengerSending")
                        : t("messengerSendFailed")}
                    </small>
                    {message.state === "failed" && (
                      <button
                        type="button"
                        onClick={() => {
                          setPending((current) =>
                            current.map((item) =>
                              item.clientMessageId === message.clientMessageId
                                ? { ...item, state: "sending" }
                                : item,
                            ),
                          );
                          send.mutate({ ...message, state: "sending" });
                        }}
                      >
                        {t("messengerRetry")}
                      </button>
                    )}
                  </span>
                </div>
              ))}
              {!messages.isPending && messages.data?.messages.length === 0 && (
                <div className="messenger-empty messenger-empty--history">
                  <strong>{t("messengerNoMessages")}</strong>
                  <p>{t("messengerFirstMessage")}</p>
                </div>
              )}
              <div ref={messageEnd} />
            </div>
            {Object.keys(typingUsers).some(
              (id) => Number(id) !== me.data.id,
            ) && (
              <p className="messenger-typing" aria-live="polite">
                {t("messengerTyping")}
              </p>
            )}
            <form className="messenger-composer" onSubmit={submitMessage}>
              {(replyTo || editing || forwarding) && (
                <div className="messenger-composer__context">
                  <strong>
                    {editing
                      ? t("messengerEditing")
                      : forwarding
                        ? t("messengerForwarding")
                        : t("messengerReplying")}
                  </strong>
                  <span>
                    {(editing ?? forwarding ?? replyTo)?.body.slice(0, 160)}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setReplyTo(null);
                      setForwarding(null);
                      if (editing) setDraft("");
                      setEditing(null);
                    }}
                    aria-label={t("close")}
                  >
                    ×
                  </button>
                </div>
              )}
              {attachments.map((asset) => (
                <span className="messenger-composer__file" key={asset.id}>
                  {asset.original_name}
                  <button
                    type="button"
                    onClick={() =>
                      setAttachments((current) =>
                        current.filter((item) => item.id !== asset.id),
                      )
                    }
                  >
                    ×
                  </button>
                </span>
              ))}
              {uploading && <progress aria-label={t("messengerUploading")} />}
              {composerError && (
                <p role="alert">{t("messengerComposerError")}</p>
              )}
              <label className="sr-only" htmlFor="messenger-message-body">
                {t("messengerMessage")}
              </label>
              <textarea
                id="messenger-message-body"
                value={draft}
                maxLength={10_000}
                rows={1}
                placeholder={t("messengerMessagePlaceholder")}
                onChange={(event) => announceTyping(event.target.value)}
                onKeyDown={handleComposerKey}
              />
              {!editing && (
                <label className="messenger-upload-button">
                  <span>{t("messengerAttach")}</span>
                  <input
                    type="file"
                    accept=".png,.jpg,.jpeg,.gif,.webp,.mp4,.pdf,.docx,.xlsx"
                    disabled={uploading || attachments.length >= 10}
                    onChange={(event) => {
                      void uploadAttachment(event.target.files?.[0]);
                      event.target.value = "";
                    }}
                  />
                </label>
              )}
              <button
                className="button"
                type="submit"
                disabled={
                  uploading ||
                  (!draft.trim() && !attachments.length && !forwarding)
                }
              >
                {t("sendComment")}
              </button>
            </form>
          </>
        ) : (
          <div className="messenger-empty messenger-empty--thread">
            <strong>{t("messengerChooseConversation")}</strong>
            <p>{t("messengerChooseConversationDescription")}</p>
          </div>
        )}
      </article>

      {dialog && (
        <NewConversationDialog
          mode={dialog}
          onClose={() => setDialog(null)}
          onCreated={(conversation) => {
            queryClient.setQueryData<CursorPage<MessengerConversation>>(
              ["messenger-conversations"],
              (current) => {
                const normalized: MessengerConversation = {
                  ...conversation,
                  peer:
                    conversation.peer ??
                    conversation.members?.find(
                      (row) => row.user.id !== me.data?.id,
                    )?.user ??
                    null,
                  member_count:
                    conversation.member_count ??
                    conversation.members?.length ??
                    0,
                  activity_at:
                    conversation.activity_at ??
                    conversation.last_message_at ??
                    conversation.created_at ??
                    new Date().toISOString(),
                  state: conversation.state ?? {
                    is_archived: false,
                    pinned_at: null,
                    muted_until: null,
                    draft_body: "",
                    draft_updated_at: null,
                  },
                  unread_count: conversation.unread_count ?? 0,
                  last_message: conversation.last_message ?? null,
                };
                return {
                  next: current?.next ?? null,
                  previous: current?.previous ?? null,
                  results: [
                    normalized,
                    ...(current?.results ?? []).filter(
                      (item) => item.id !== conversation.id,
                    ),
                  ],
                };
              },
            );
            selectConversation(conversation);
            setDialog(null);
          }}
        />
      )}
    </section>
  );
}
