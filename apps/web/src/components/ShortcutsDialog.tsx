import { useLayoutEffect, useRef } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
}

const GROUPS: { title: string; items: [string, string][] }[] = [
  {
    title: "搜索",
    items: [
      ["/", "聚焦搜索框"],
      ["Ctrl / ⌘ K", "聚焦搜索框，并重新展开建议"],
      ["Enter", "提交搜索或打开选中结果"],
      ["Esc", "关闭面板 / 取消当前选择"],
    ],
  },
  {
    title: "浏览结果",
    items: [
      ["j / k", "下一条 / 上一条结果"],
      ["[ / ]", "上一页 / 下一页"],
      ["g h", "回到搜索首页"],
      ["g b", "打开书签启动台"],
      ["?", "打开这张快捷键速查表"],
    ],
  },
  {
    title: "结果操作",
    items: [
      ["b", "收藏当前选中结果"],
      ["s", "对当前结果生成 AI 总结"],
    ],
  },
];

/** 快捷键速查表：原生 dialog 提供焦点圈定、Esc 关闭与遮罩点击关闭。 */
export default function ShortcutsDialog({ open, onClose }: Props) {
  const node = useRef<HTMLDialogElement>(null);
  const backdropPressed = useRef(false);

  useLayoutEffect(() => {
    const dialog = node.current;
    if (!dialog) return;
    dialog.setAttribute("closedby", "any");
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={node}
      className="shortcuts-dialog"
      aria-labelledby="shortcuts-title"
      onClose={event => {
        if (open && !event.currentTarget.open) onClose();
      }}
      onPointerDown={event => { backdropPressed.current = event.target === event.currentTarget; }}
      onClick={(event) => {
        const dialog = event.currentTarget;
        if (Reflect.has(dialog, "closedBy") || !backdropPressed.current || event.target !== dialog) return;
        const { left, right, top, bottom } = dialog.getBoundingClientRect();
        if (event.clientX < left || event.clientX > right || event.clientY < top || event.clientY > bottom) dialog.close();
      }}
    >
      <div className="shortcuts-dialog__head">
        <h2 id="shortcuts-title">键盘快捷键</h2>
        <button type="button" className="shortcuts-dialog__close" autoFocus onClick={() => node.current?.close()}>关闭</button>
      </div>
      <div className="shortcuts-dialog__body">
        {GROUPS.map((group) => (
          <section key={group.title}>
            <h3>{group.title}</h3>
            <dl>
              {group.items.map(([keys, text]) => (
                <div key={keys}>
                  <dt>{keys.split(" / ").map((key) => <kbd key={key}>{key}</kbd>)}</dt>
                  <dd>{text}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
        <p className="shortcuts-dialog__foot">移动端不显示键盘提示；外接键盘下这些键仍然有效。</p>
      </div>
    </dialog>
  );
}
