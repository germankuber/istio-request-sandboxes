import { useEffect } from "react";

interface ConfirmDeleteModalProps {
  name: string;
  onConfirm: (name: string) => void;
  onCancel: () => void;
}

export function ConfirmDeleteModal({ name, onConfirm, onCancel }: ConfirmDeleteModalProps) {
  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onCancel]);

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-delete-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h3 id="confirm-delete-title">Delete sandbox "{name}"?</h3>
        <p>
          Its deployments, routes and mock rules will be removed. Requests with{" "}
          <code>X-Sandbox-ID: {name}</code> will fall back to baseline.
        </p>
        <div className="modal-actions">
          <button onClick={onCancel} autoFocus>
            cancel
          </button>
          <button className="danger" onClick={() => onConfirm(name)}>
            delete
          </button>
        </div>
      </div>
    </div>
  );
}
