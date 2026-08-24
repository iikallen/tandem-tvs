import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import {
  api,
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
  state: "sending" | "failed";
};

type NewConversationMode = "direct" | "group";

function conversationTitle(
  conversation: MessengerConversation,
  currentUserId: number,
): string {
  if (conversation.type === "GROUP") return conversation.title;
  return (
    conversation.members.find(
      (membership) => membership.user.id !== currentUserId,
    )?.user.full_name ?? t("messengerUnknownPerson")
  );
}

function conversationSubtitle(
  conversation: MessengerConversation,
  currentUserId: number,
): string {
  if (conversation.last_message) {
    const prefix =
      conversation.last_message.author.id === currentUserId
        ? t("messengerYou")
        : conversation.last_message.author.full_name.split(" ")[0];
    return `${prefix}: ${conversation.last_message.body}`;
  }
  return conversation.type === "GROUP"
    ? t("messengerMemberCount", { count: conversation.members.length })
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
    return message.receipt.read ? t("messengerRead") : t("messengerDelivered");
  }
  return t("messengerReadCount", {
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
  const searchInput = useRef<HTMLInputElement>(null);
  const people = useQuery({
    queryKey: ["messenger-people", debouncedSearch],
    queryFn: () => api.messengerPeople(debouncedSearch),
  });
  const create = useMutation({
    mutationFn: (person?: MessengerPerson) =>
      mode === "direct" && person
        ? api.createDirectConversation(person.id)
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

  return (
    <div className="dialog-scrim" role="presentation" onMouseDown={onClose}>
      <section
        className="messenger-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="messenger-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "Escape") onClose();
        }}
      >
        <header className="messenger-dialog__header">
          <div>
            <p className="overline">{t("messenger")}</p>
            <h2 id="messenger-dialog-title">
              {mode === "direct"
                ? t("messengerStartDirect")
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
        {mode === "group" && (
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
              {mode === "group" && (
                <input
                  type="checkbox"
                  checked={members.includes(person.id)}
                  onChange={() =>
                    setMembers((current) =>
                      current.includes(person.id)
                        ? current.filter((id) => id !== person.id)
                        : [...current, person.id],
                    )
                  }
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
            </label>
          ))}
          {!people.isPending && people.data?.length === 0 && (
            <p>{t("messengerPeopleEmpty")}</p>
          )}
        </div>
        {create.isError && <p role="alert">{t("messengerCreateFailed")}</p>}
        {mode === "group" && (
          <form className="messenger-dialog__actions" onSubmit={submitGroup}>
            <span>
              {t("messengerSelectedCount", { count: members.length })}
            </span>
            <button
              className="button"
              type="submit"
              disabled={!title.trim() || !members.length || create.isPending}
            >
              {t("messengerCreateGroup")}
            </button>
          </form>
        )}
      </section>
    </div>
  );
}

export function MessengerAccessPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<NewConversationMode | null>(null);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<PendingMessage[]>([]);
  const [realtime, setRealtime] = useState<
    "connecting" | "connected" | "stopped"
  >("connecting");
  const messageEnd = useRef<HTMLDivElement>(null);
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const conversations = useQuery({
    queryKey: ["messenger-conversations"],
    queryFn: api.messengerConversations,
  });
  const selected = conversations.data?.find(
    (conversation) => conversation.id === selectedId,
  );
  const messages = useQuery({
    queryKey: ["messenger-messages", selectedId],
    queryFn: () => api.messengerMessages(selectedId ?? ""),
    enabled: Boolean(selectedId),
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

    async function connect() {
      setRealtime("connecting");
      try {
        const { ticket } = await api.messengerRealtimeTicket();
        if (stopped) return;
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(
          `${protocol}//${window.location.host}/ws/v1/messenger?ticket=${encodeURIComponent(ticket)}`,
        );
        socket.onopen = () => setRealtime("connected");
        socket.onmessage = (event) => {
          let hint: { type?: string; conversation_id?: string };
          try {
            hint = JSON.parse(String(event.data)) as typeof hint;
          } catch {
            return;
          }
          if (!hint.type?.startsWith("messenger.")) return;
          void queryClient.invalidateQueries({
            queryKey: ["messenger-conversations"],
          });
          if (hint.conversation_id) {
            void queryClient.invalidateQueries({
              queryKey: ["messenger-messages", hint.conversation_id],
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
          reconnectTimer = window.setTimeout(connect, 1_000);
        };
      } catch {
        if (!stopped) reconnectTimer = window.setTimeout(connect, 1_000);
      }
    }

    void connect();
    return () => {
      stopped = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [queryClient]);

  const newestSequence = messages.data?.messages.at(-1)?.sequence ?? 0;
  useEffect(() => {
    if (!selectedId || !selected?.unread_count || newestSequence < 1) return;
    let active = true;
    void api
      .markMessengerRead(selectedId, newestSequence)
      .then(() => {
        if (!active) return;
        queryClient.setQueryData<MessengerConversation[]>(
          ["messenger-conversations"],
          (current) =>
            current?.map((conversation) =>
              conversation.id === selectedId
                ? { ...conversation, unread_count: 0 }
                : conversation,
            ),
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

  const send = useMutation({
    mutationFn: (message: PendingMessage) =>
      api.sendMessengerMessage(
        message.conversationId,
        message.clientMessageId,
        message.body,
      ),
    onSuccess: (saved, optimistic) => {
      queryClient.setQueryData<MessengerMessagePage>(
        ["messenger-messages", optimistic.conversationId],
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

  function submitMessage(event: FormEvent) {
    event.preventDefault();
    const body = draft.trim();
    if (!selectedId || !body) return;
    const optimistic: PendingMessage = {
      conversationId: selectedId,
      clientMessageId: crypto.randomUUID(),
      body,
      state: "sending",
    };
    setDraft("");
    setPending((current) => [...current, optimistic]);
    send.mutate(optimistic);
  }

  function handleComposerKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  const selectedTitle = useMemo(
    () => (selected && me.data ? conversationTitle(selected, me.data.id) : ""),
    [me.data, selected],
  );

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
        </div>
        <div className="messenger-conversations">
          {conversations.data?.map((conversation) => {
            const title = conversationTitle(conversation, me.data.id);
            const peer = conversation.members.find(
              (membership) => membership.user.id !== me.data.id,
            )?.user;
            return (
              <button
                key={conversation.id}
                className={`messenger-conversation${conversation.id === selectedId ? " is-active" : ""}`}
                type="button"
                onClick={() => setSelectedId(conversation.id)}
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
          {conversations.data?.length === 0 && (
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
                        count: selected.members.length,
                      })
                    : selected.members.find(
                        (membership) => membership.user.id !== me.data.id,
                      )?.user.job_title || t("messengerDirect")}
                </p>
              </div>
            </header>
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
                      ["messenger-messages", selected.id],
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
                    className={`messenger-message${mine ? " messenger-message--mine" : ""}`}
                    key={message.id}
                  >
                    {!mine && <strong>{message.author.full_name}</strong>}
                    <p>{message.body}</p>
                    <span>
                      <time dateTime={message.created_at}>
                        {shortTime(message.created_at)}
                      </time>
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
            <form className="messenger-composer" onSubmit={submitMessage}>
              <label className="sr-only" htmlFor="messenger-message-body">
                {t("messengerMessage")}
              </label>
              <textarea
                id="messenger-message-body"
                value={draft}
                maxLength={10_000}
                rows={1}
                placeholder={t("messengerMessagePlaceholder")}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={handleComposerKey}
              />
              <button className="button" type="submit" disabled={!draft.trim()}>
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
            queryClient.setQueryData<MessengerConversation[]>(
              ["messenger-conversations"],
              (current) => [
                conversation,
                ...(current ?? []).filter(
                  (item) => item.id !== conversation.id,
                ),
              ],
            );
            setSelectedId(conversation.id);
            setDialog(null);
          }}
        />
      )}
    </section>
  );
}
