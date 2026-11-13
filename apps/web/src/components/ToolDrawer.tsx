import { useLayoutEffect, useRef } from "react";
import type { ReactNode } from "react";

interface Props {
  id: string;
  open: boolean;
  label: string;
  onClose: () => void;
  children: ReactNode;
}

/**
 * 移动端工具抽屉：原生 <dialog> 提供焦点圈定、Esc 关闭与惰性背景，
 * 底部弹出且不参与文档流，因此打开时结果区位置不变。
 */
export default function ToolDrawer({ id, open, label, onClose, children }: Props) {
  const node = useRef<HTMLDialogElement>(null);
  const backdropPressed = useRef(false);

  useLayoutEffect(() => {
    const dialog = node.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.setAttribute("closedby", "any");
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      id={id}
      ref={node}
      className="tool-drawer"
      aria-label={label}
      onClose={(event) => {
        if (open && !event.currentTarget.open) onClose();
      }}
      onPointerDown={(event) => {
        backdropPressed.current = event.target === event.currentTarget;
      }}
      onClick={(event) => {
        const dialog = event.currentTarget;
        if (Reflect.has(dialog, "closedBy") || !backdropPressed.current || event.target !== dialog) return;
        const { left, right, top, bottom } = dialog.getBoundingClientRect();
        if (event.clientX < left || event.clientX > right || event.clientY < top || event.clientY > bottom) {
          dialog.close();
        }
      }}
    >
      <div className="tool-drawer__sheet">
        <div className="tool-drawer__head">
          <h2>{label}</h2>
          <button type="button" className="tool-drawer__close" autoFocus onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="tool-drawer__body">{children}</div>
      </div>
    </dialog>
  );
}
