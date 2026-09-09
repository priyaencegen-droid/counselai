import { FileText, Trash2 } from 'lucide-react'
export default function FileList({files,onRemove}:{files:File[];onRemove:(index:number)=>void}) {
  return <div className="mt-5 space-y-2">
    {files.map((file,index)=><div key={`${file.name}-${file.size}-${index}`} className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800"><FileText size={18}/></div>
      <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{file.name}</p><p className="mt-1 text-xs text-slate-500">{(file.size/1024/1024).toFixed(2)} MB · {file.name.split('.').pop()?.toUpperCase()}</p></div>
      <button onClick={()=>onRemove(index)} className="rounded-xl p-2 text-slate-500 hover:bg-slate-100 hover:text-red-600 dark:hover:bg-slate-800"><Trash2 size={17}/></button>
    </div>)}
  </div>
}
