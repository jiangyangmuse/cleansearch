import type { Result, ResultCategory } from "../types";
import ResultList from "./ResultList";

const modules: { category: ResultCategory; title: string }[] = [
  { category: "encyclopedia", title: "百科" },
  { category: "download", title: "应用下载" },
  { category: "video", title: "视频" },
];

export function contentModules(results: Result[]) {
  return modules.map(module => ({
    ...module,
    results: results.filter(result => result.category === module.category),
  }));
}

export default function ContentModules({ results, selectedId, onSelect }: {
  results: Result[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return contentModules(results).map(module => (
    <ResultList key={module.category} title={module.title} results={module.results}
      selectedId={selectedId} onSelect={onSelect} />
  ));
}
