import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
export default function MarkdownReport({content}:{content:string}) {
  return <article className="legal-report prose prose-slate max-w-none dark:prose-invert prose-headings:tracking-tight prose-table:text-sm prose-th:bg-slate-100 dark:prose-th:bg-slate-800">
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
  </article>
}
