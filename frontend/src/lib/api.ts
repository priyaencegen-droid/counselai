export type Job = {
  id: string
  status: string
  progress: number
  current_step: string
  total_files: number
  processed_files: number
  error?: string | null
  completed_at?: string | null
  report_id?: number | null
}

export type Report = {
  id: number
  job_id: string
  title: string
  document_count: number
  created_at: string
  markdown?: string
}

const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init)
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const message = typeof body?.detail === 'string' ? body.detail : body?.detail?.message || 'Request failed'
    throw new Error(message)
  }
  return body as T
}

export async function uploadFiles(files: File[], onProgress?: (value:number)=>void) {
  const form = new FormData()
  files.forEach(file => form.append('files', file))
  return new Promise<{job_id:string;files:any[];rejected:any[]}>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_URL}/upload`)
    xhr.upload.onprogress = event => { if (event.lengthComputable) onProgress?.(Math.round(event.loaded / event.total * 100)) }
    xhr.onload = () => {
      try { const data = JSON.parse(xhr.responseText); if (xhr.status >= 200 && xhr.status < 300) resolve(data); else reject(new Error(data.detail?.message || data.detail || 'Upload failed')) }
      catch { reject(new Error('Invalid server response')) }
    }
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.send(form)
  })
}

export const startAnalysis = (jobId:string, title?:string) => request<Job>('/analyze', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({job_id:jobId,title:title || null})})
export const getJob = (jobId:string) => request<Job>(`/jobs/${jobId}`)
export const getReports = () => request<Report[]>('/reports')
export const getReport = (id:number) => request<Report>(`/reports/${id}`)
export const health = () => request<{status:string;provider:string}>('/health')
