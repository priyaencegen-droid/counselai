import { useRef, useState } from 'react'
import { FileUp } from 'lucide-react'

export default function Dropzone({onFiles}:{onFiles:(files:File[])=>void}) {
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const choose = (files:FileList | null) => files && onFiles(Array.from(files))
  return <div
    onDragEnter={e=>{e.preventDefault();setDragging(true)}}
    onDragOver={e=>e.preventDefault()}
    onDragLeave={()=>setDragging(false)}
    onDrop={e=>{e.preventDefault();setDragging(false);choose(e.dataTransfer.files)}}
    className={`rounded-3xl border-2 border-dashed p-10 text-center transition ${dragging ? 'border-slate-900 bg-slate-100 dark:border-white dark:bg-slate-800' : 'border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900'}`}
  >
    <input ref={input} hidden type="file" accept=".pdf,.docx,.xls,.xlsx,.txt" multiple onChange={e=>choose(e.target.files)} />
    <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 dark:bg-slate-800"><FileUp size={26}/></div>
    <h3 className="mt-5 text-lg font-bold">Drop legal documents here</h3>
    <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">Upload PDF, DOCX, XLS, XLSX or TXT files. Each file is validated and processed independently.</p>
    <button onClick={()=>input.current?.click()} className="mt-6 rounded-xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white dark:bg-white dark:text-slate-950">Choose documents</button>
  </div>
}
