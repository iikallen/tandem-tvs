import { useEffect, useRef } from "react";

export function ConfirmDialog({
  open,
  title,
  consequence,
  confirmLabel,
  busy = false,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  consequence: string;
  confirmLabel: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (open) cancel.current?.focus();
  }, [open]);
  if (!open) return null;
  return (
    <div
      className="dialog-scrim"
      role="presentation"
      onMouseDown={(event) =>
        event.target === event.currentTarget && !busy && onCancel()
      }
    >
      <section
        className="confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
      >
        <h2 id="confirm-title">{title}</h2>
        <p>{consequence}</p>
        <div className="button-row">
          <button
            ref={cancel}
            className="button button--secondary"
            type="button"
            disabled={busy}
            onClick={onCancel}
          >
            Отмена
          </button>
          <button
            className="button button--danger"
            type="button"
            disabled={busy}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
