import { useEffect, useState } from "react";

interface Props {
  query: string;
  startedAt: number;
}

export function SearchProgress({ className, label, startedAt }: {
  className: string;
  label: string;
  startedAt: number;
}) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setElapsed(performance.now() - startedAt), 100);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  return <p className={className} aria-hidden="true">{label}… {(elapsed / 1000).toFixed(1)}s</p>;
}

/** 结果区骨架：3 张卡占位，避免加载时高度塌陷与 CLS。 */
export default function ResultSkeleton({ query, startedAt }: Props) {
  return (
    <div className="skeleton">
      <SearchProgress className="skeleton__status" label={`正在检索「${query}」`} startedAt={startedAt} />
      <div className="skeleton__cards" aria-hidden="true">
        {[0, 1, 2].map((index) => (
          <div className="skeleton__card" key={index}>
            <div className="skeleton__row skeleton__row--meta" />
            <div className="skeleton__row skeleton__row--title" />
            <div className="skeleton__row skeleton__row--line" />
            <div className="skeleton__row skeleton__row--line skeleton__row--short" />
          </div>
        ))}
      </div>
    </div>
  );
}
