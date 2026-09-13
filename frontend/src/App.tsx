import { useState } from 'react'

const API_URL = 'https://document-qa-rag-1p15.onrender.com'

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState<any>(null)

  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [answer, setAnswer] = useState<any>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) setFile(e.target.files[0])
  }

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const response = await fetch(`${API_URL}/upload`, { method: 'POST', body: formData })
      setUploadResult(await response.json())
    } catch {
      setUploadResult({ error: 'Upload failed. Check console.' })
    } finally {
      setUploading(false)
    }
  }

  const handleAsk = async () => {
    if (!question.trim()) return
    setAsking(true)
    try {
      const response = await fetch(`${API_URL}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: question }),
      })
      setAnswer(await response.json())
    } catch {
      setAnswer({ error: 'Failed to get answer. Check console.' })
    } finally {
      setAsking(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
      <div className="w-full max-w-xl bg-white rounded-2xl shadow-md p-8">
        <h1 className="text-2xl font-semibold text-gray-900 mb-6">Document Q&A</h1>

        <div className="mb-8">
          <h2 className="text-sm font-medium text-gray-500 mb-2">1. Upload a PDF</h2>
          <div className="flex items-center gap-3">
            <input
              type="file"
              accept=".pdf"
              onChange={handleFileChange}
              className="text-sm text-gray-600 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-blue-50 file:text-blue-700 file:text-sm"
            />
            <button
              onClick={handleUpload}
              disabled={!file || uploading}
              className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium disabled:bg-gray-300 disabled:cursor-not-allowed hover:bg-blue-700 transition"
            >
              {uploading ? 'Uploading...' : 'Upload'}
            </button>
          </div>
          {uploadResult && (
            <p className="mt-3 text-sm text-gray-600">
              {uploadResult.error ?? `Uploaded "${uploadResult.filename}" — ${uploadResult.num_chunks} chunks stored.`}
            </p>
          )}
        </div>

        <div>
          <h2 className="text-sm font-medium text-gray-500 mb-2">2. Ask a question</h2>
          <div className="flex items-center gap-3">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What do you want to know?"
              className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={handleAsk}
              disabled={!question.trim() || asking}
              className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium disabled:bg-gray-300 disabled:cursor-not-allowed hover:bg-blue-700 transition"
            >
              {asking ? 'Thinking...' : 'Ask'}
            </button>
          </div>

          {answer && (
            <div className="mt-4 bg-blue-50 rounded-xl p-4">
              {answer.error ? (
                <p className="text-sm text-red-600">{answer.error}</p>
              ) : (
                <>
                  <p className="text-sm text-gray-800"><span className="font-medium">Answer:</span> {answer.answer}</p>
                  <details className="mt-2">
                    <summary className="text-xs text-gray-500 cursor-pointer">Chunks used ({answer.chunks_used.length})</summary>
                    {answer.chunks_used.map((chunk: string, i: number) => (
                      <p key={i} className="text-xs text-gray-500 mt-1">{chunk}</p>
                    ))}
                  </details>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default App