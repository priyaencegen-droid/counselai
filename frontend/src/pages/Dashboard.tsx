import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, Clock3, Copy, FileSearch, Moon, Play, Plus, Printer, RefreshCw, RotateCcw, Sun } from 'lucide-react'
import Dropzone from '../components/Dropzone'
import FileList from '../components/FileList'
import MarkdownReport from '../components/MarkdownReport'
import { getJob, getReport, getReports, startAnalysis, uploadFiles, type Job, type Report } from '../lib/api'

const MAX_FILES = 100

export default function Dashboard() {
  const [files, setFiles] = useState<File[]>([])
  const [uploadProgress, setUploadProgress] = useState(0)
  const [job, setJob] = useState<Job | null>(null)
  const [reports, setReports] = useState<Report[]>([])
  const [active, setActive] = useState<Report | null>(null)
  const [busy, setBusy] = useState(false)
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark')
  const [error, setError] = useState('')
  const [title, setTitle] = useState('')

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  useEffect(() => {
    getReports().then(setReports).catch(() => {})
  }, [])

  useEffect(() => {
    if (!job || !['queued', 'processing'].includes(job.status)) return
    const timer = window.setInterval(() => {
      getJob(job.id)
        .then(updated => {
          setJob(updated)
          if (updated.status === 'completed' && updated.report_id) {
            getReport(updated.report_id).then(setActive)
            getReports().then(setReports)
          }
        })
        .catch(e => setError(e.message))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [job?.id, job?.status])

  const addFiles = (incoming: File[]) => {
    setError('')
    setFiles(prev => {
      const combined = [...prev, ...incoming].filter((f, i, a) => i === a.findIndex(x => x.name === f.name && x.size === f.size))
      if (combined.length > MAX_FILES) {
        setError(`Maximum ${MAX_FILES} files per batch.`)
        return combined.slice(0, MAX_FILES)
      }
      return combined
    })
  }

  const uploadBatch = async () => {
    if (!files.length) return
    try {
      setBusy(true)
      setError('')
      setUploadProgress(0)
      const result = await uploadFiles(files, setUploadProgress)
      setJob({
        id: result.job_id,
        status: 'uploaded',
        progress: 10,
        current_step: 'Files uploaded successfully',
        total_files: result.files.length,
        processed_files: 0,
      })
      setFiles([])
      setUploadProgress(100)
      if (result.rejected.length) {
        setError(result.rejected.map(x => `${x.filename}: ${x.reason}`).join('\n'))
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const analyze = async () => {
    if (!job) return
    try {
      setBusy(true)
      setError('')
      const updated = await startAnalysis(job.id, title)
      setJob(updated)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const resetWorkspace = () => {
    setJob(null)
    setFiles([])
    setUploadProgress(0)
    setError('')
    setTitle('')
  }

  const openReport = async (id: number) => {
    try {
      setError('')
      setActive(await getReport(id))
    } catch (e: any) {
      setError(e.message)
    }
  }

  const copy = async () => {
    if (active?.markdown) {
      await navigator.clipboard.writeText(active.markdown)
    }
  }

  const status = useMemo(() => {
    const map: Record<string, [string, string]> = {
      uploaded: ['Ready for Analysis', 'Files validated and ready'],
      queued: ['Queued', 'Waiting for analysis worker'],
      processing: ['Analyzing Documents', 'Extracting, chunking, and querying model'],
      completed: ['Report Ready', 'Legal title search report generated'],
      failed: ['Analysis Failed', 'Encountered an issue during processing'],
    }
    return map[job?.status || 'uploaded'] || ['Ready', '']
  }, [job?.status])

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950 dark:bg-slate-950 dark:text-slate-100">
      <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-slate-950 p-2.5 text-white dark:bg-white dark:text-slate-950">
              <FileSearch size={21} />
            </div>
            <div>
              <div className="font-bold">CounselAI</div>
              <div className="text-xs text-slate-500">Legal Document & Title Intelligence</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {job && (
              <button
                onClick={resetWorkspace}
                className="flex items-center gap-1.5 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-900"
              >
                <Plus size={14} /> New Analysis
              </button>
            )}
            <button
              onClick={() => setDark(x => !x)}
              className="rounded-xl border border-slate-200 p-2.5 dark:border-slate-800"
              aria-label="Toggle Theme"
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 px-5 py-8 lg:grid-cols-[1.15fr_.85fr] lg:px-8">
        <section>
          <div className="mb-6">
            <div className="text-xs font-bold uppercase tracking-[.18em] text-slate-500">Document Workspace</div>
            <h1 className="mt-2 text-3xl font-black tracking-tight">Cross-Document Legal Review</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
              Upload multi-format document sets (PDF, DOCX, XLS, XLSX, TXT) to parse data, cross-check mutations, and generate structured Title Search Reports.
            </p>
          </div>

          <Dropzone onFiles={addFiles} />

          {files.length > 0 && (
            <div className="mt-5 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between">
                <h2 className="font-bold">Selected documents</h2>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold dark:bg-slate-800">
                  {files.length} {files.length === 1 ? 'file' : 'files'}
                </span>
              </div>
              <FileList files={files} onRemove={i => setFiles(x => x.filter((_, idx) => idx !== i))} />
              <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto]">
                <input
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  placeholder="Optional report title (e.g. Title Search Gat 12/13)"
                  className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-slate-300 dark:border-slate-700 dark:bg-slate-950"
                />
                <button
                  disabled={busy}
                  onClick={uploadBatch}
                  className="rounded-xl bg-slate-950 px-5 py-3 text-sm font-bold text-white disabled:opacity-50 dark:bg-white dark:text-slate-950"
                >
                  {busy ? 'Uploading…' : `Upload ${files.length} file${files.length > 1 ? 's' : ''}`}
                </button>
              </div>
            </div>
          )}

          {uploadProgress > 0 && uploadProgress < 100 && (
            <Progress label="Uploading documents" value={uploadProgress} />
          )}

          {job && (
            <div className="mt-6 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 font-bold">
                    {job.status === 'completed' ? (
                      <CheckCircle2 className="text-emerald-600" size={19} />
                    ) : job.status === 'failed' ? (
                      <AlertCircle className="text-red-500" size={19} />
                    ) : (
                      <Clock3 className="animate-spin text-blue-500" size={19} />
                    )}
                    {status[0]}
                  </div>
                  <p className="mt-1 text-sm text-slate-500">{job.current_step || status[1]}</p>
                </div>

                <div className="flex items-center gap-2">
                  {job.status === 'uploaded' && (
                    <button
                      disabled={busy}
                      onClick={analyze}
                      className="flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50 dark:bg-white dark:text-slate-950"
                    >
                      <Play size={15} /> Analyze
                    </button>
                  )}
                  {job.status === 'failed' && (
                    <button
                      disabled={busy}
                      onClick={analyze}
                      className="flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-red-700 disabled:opacity-50"
                    >
                      <RotateCcw size={15} /> Retry
                    </button>
                  )}
                </div>
              </div>

              <Progress
                label={job.total_files > 0 ? `${job.processed_files}/${job.total_files} files parsed` : 'Processing'}
                value={job.progress}
              />

              {job.error && (
                <div className="mt-4 rounded-xl bg-red-50 p-4 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">
                  <div className="font-semibold">Error Details:</div>
                  <pre className="mt-1 whitespace-pre-wrap font-mono">{job.error}</pre>
                </div>
              )}
            </div>
          )}

          {active && (
            <div className="mt-6 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 print:shadow-none">
              <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-xl font-black">{active.title}</h2>
                  <p className="mt-1 text-xs text-slate-500">
                    {active.document_count} documents · {new Date(active.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="flex gap-2 print:hidden">
                  <button
                    onClick={copy}
                    className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold dark:border-slate-700"
                  >
                    <Copy size={15} /> Copy
                  </button>
                  <button
                    onClick={() => {
                      const blob = new Blob([active.markdown || ''], { type: 'text/plain' })
                      const a = document.createElement('a')
                      a.href = URL.createObjectURL(blob)
                      a.download = `${active.title.toLowerCase().replace(/[^a-z0-9]/g, '-')}.txt`
                      a.click()
                      URL.revokeObjectURL(a.href)
                    }}
                    className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold dark:border-slate-700"
                  >
                    Export TXT
                  </button>
                  <button
                    onClick={() => window.print()}
                    className="flex items-center gap-2 rounded-xl bg-slate-950 px-3 py-2 text-sm font-semibold text-white dark:bg-white dark:text-slate-950"
                  >
                    <Printer size={15} /> PDF
                  </button>
                </div>
              </div>
              <MarkdownReport content={active.markdown || ''} />
            </div>
          )}
        </section>

        <aside className="space-y-4 lg:sticky lg:top-24 lg:h-fit print:hidden">
          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between">
              <h2 className="font-black">Report History</h2>
              <button
                onClick={() => getReports().then(setReports)}
                className="rounded-lg p-2 hover:bg-slate-100 dark:hover:bg-slate-800"
                aria-label="Refresh Reports"
              >
                <RefreshCw size={17} />
              </button>
            </div>
            {reports.length === 0 ? (
              <p className="py-10 text-center text-sm text-slate-500">No reports generated yet.</p>
            ) : (
              <div className="mt-4 space-y-2">
                {reports.map(report => (
                  <button
                    key={report.id}
                    onClick={() => openReport(report.id)}
                    className={`w-full rounded-2xl border p-4 text-left transition ${
                      active?.id === report.id
                        ? 'border-slate-950 bg-slate-100 dark:border-white dark:bg-slate-800'
                        : 'border-slate-200 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800'
                    }`}
                  >
                    <div className="truncate text-sm font-bold">{report.title}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {report.document_count} files · {new Date(report.created_at).toLocaleDateString()}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
            <h3 className="font-black">Legal Intelligence Pipeline</h3>
            <ol className="mt-4 space-y-3 text-sm text-slate-500">
              <li><b className="text-slate-900 dark:text-white">01</b> Multi-format ingestion (PDF, DOCX, XLS, XLSX, TXT)</li>
              <li><b className="text-slate-900 dark:text-white">02</b> Multi-encoding & table structure extraction</li>
              <li><b className="text-slate-900 dark:text-white">03</b> Source-tagged chunk aggregation</li>
              <li><b className="text-slate-900 dark:text-white">04</b> Cross-document evidence batch mapping</li>
              <li><b className="text-slate-900 dark:text-white">05</b> Contradiction detection & synthesis</li>
              <li><b className="text-slate-900 dark:text-white">06</b> Structured Title Search Report generation</li>
            </ol>
          </div>

          {error && (
            <div className="whitespace-pre-wrap rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
              {error}
            </div>
          )}
        </aside>
      </main>
    </div>
  )
}

function Progress({ label, value }: { label: string; value: number }) {
  return (
    <div className="mt-5">
      <div className="mb-2 flex justify-between text-xs text-slate-500">
        <span>{label}</span>
        <span>{Math.min(100, Math.max(0, value))}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        <div
          className="h-full rounded-full bg-slate-950 transition-all dark:bg-white"
          style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
        />
      </div>
    </div>
  )
}
