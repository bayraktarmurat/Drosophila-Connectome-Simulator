import { useEffect } from "react";
import type { ReactNode } from "react";

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}

/** Centered overlay window; Escape or the backdrop closes it. */
export default function Modal(props: ModalProps) {
  const onClose = props.onClose;
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  let className = "modal";
  if (props.wide === true) {
    className = "modal modal-wide";
  }
  return (
    <div className="modal-backdrop" onMouseDown={props.onClose}>
      <div className={className} onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <h3>{props.title}</h3>
          <button onClick={props.onClose} aria-label="close">
            ✕
          </button>
        </div>
        <div className="modal-body">{props.children}</div>
      </div>
    </div>
  );
}
