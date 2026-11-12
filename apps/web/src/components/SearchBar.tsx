interface Props {
  value: string;
  busy: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export default function SearchBar({ value, busy, onChange, onSubmit }: Props) {
  return (
    <form
      className="searchbar"
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="searchbar__field">
        <i className="ws-icon ws-icon--search" aria-hidden="true" />
        <input
          className="searchbar__input"
          type="search"
          name="q"
          value={value}
          placeholder="输入关键词搜索"
          autoComplete="off"
          spellCheck={false}
          onChange={(event) => onChange(event.target.value)}
          aria-label="搜索查询"
        />
      </div>
      <button className="searchbar__button" type="submit" disabled={busy || !value.trim()}>
        {busy ? "搜索中…" : "搜索"}
      </button>
    </form>
  );
}
