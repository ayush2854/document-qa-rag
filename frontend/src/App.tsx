import { useState, useEffect, useRef } from 'react'

const API_URL = import.meta.env.VITE_API_URL
const isLocalEnvironment = import.meta.env.DEV

interface Message {
  role: 'user' | 'assistant'
  text: string
  sources?: { filename: string; page: number; text: string }[]
}

function App() {
  const [documents, setDocuments] = useState<string[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [mode, setMode] = useState<'cloud' | 'local'>('cloud')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const fetchDocuments = async (currentMode: string) => {
    try {
      const response = await fetch(`${API_URL}/documents?mode=${currentMode}`)
      const data = await response.json()
      setDocuments(data.documents)
    } catch (error) {
      console.error('Failed to fetch documents:', error)
    }
  }

  useEffect(() => {
    fetchDocuments(mode)
  }, [mode])

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setUploading(true)
    const formData = new FormData()
    formData.append('file', file)
    formData.append('mode', mode)

    try {
      const response = await fetch(`${API_URL}/upload`, { method: 'POST', body: formData })
      const data = await response.json()
      if (data.error) {
        alert(data.error)
      } else {
        await fetchDocuments(mode)
      }
    } catch (error) {
      console.error('Upload failed:', error)
      alert('Upload failed. Check console.')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleAsk = async () => {
    if (!question.trim()) return

    const userMessage: Message = { role: 'user', text: question }
    const currentHistory = messages.map(m => ({ role: m.role, text: m.text }))

    setMessages((prev) => [...prev, userMessage])
    setQuestion('')
    setAsking(true)

    try {
      const response = await fetch(`${API_URL}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userMessage.text,
          history: currentHistory,
          mode: mode,
        }),
      })
      const data = await response.json()
      setMessages((prev) => [...prev, { role: 'assistant', text: data.answer, sources: data.sources }])
    } catch (error) {
      setMessages((prev) => [...prev, { role: 'assistant', text: 'Something went wrong. Please try again.' }])
    } finally {
      setAsking(false)
    }
  }

  return (
    <div className="h-screen flex bg-gray-50">
      {/* Sidebar */}
      <div className="w-72 bg-white border-r border-gray-200 flex flex-col p-4">
        <h1 className="text-lg font-semibold text-gray-900 mb-4">Document Q&A</h1>

        {/* Mode Toggle Switch */}
        <div className="flex items-center gap-2 mb-1 p-1 bg-gray-100 rounded-lg">
          <button
            onClick={() => setMode('cloud')}
            className={`flex-1 py-1.5 rounded-md text-xs font-medium transition ${mode === 'cloud' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500'}`}
          >
            ☁️ Cloud (Gemini)
          </button>
          <button
            onClick={() => isLocalEnvironment && setMode('local')}
            disabled={!isLocalEnvironment}
            title={!isLocalEnvironment ? 'Requires running this project locally with Ollama installed' : ''}
            className={`flex-1 py-1.5 rounded-md text-xs font-medium transition ${mode === 'local' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500'} ${!isLocalEnvironment ? 'opacity-40 cursor-not-allowed' : ''}`}
          >
            🔒 Local (Private)
          </button>
        </div>
        {!isLocalEnvironment && (
          <p className="text-xs text-gray-400 mb-3">Local mode needs Ollama running on your machine — clone the repo to try it.</p>
        )}

        <input type="file" accept=".pdf" ref={fileInputRef} onChange={handleFileSelect} className="hidden" />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="w-full mb-4 px-3 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:bg-gray-300 transition"
        >
          {uploading ? 'Uploading...' : '+ Upload PDF'}
        </button>

        <div className="flex-1 overflow-y-auto">
          <h2 className="text-xs font-medium text-gray-400 uppercase mb-2">Documents ({documents.length})</h2>
          <div className="space-y-1">
            {documents.length === 0 && <p className="text-sm text-gray-400">No documents yet</p>}
            {documents.map((doc) => (
              <div key={doc} className="px-3 py-2 rounded-lg bg-blue-50 text-sm text-gray-700 truncate">
                {doc}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col">
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 && (
            <p className="text-sm text-gray-400 text-center mt-12">Upload a document and ask a question to get started.</p>
          )}
          {messages.map((msg, i) => (
            <div key={i}>
              {msg.role === 'user' ? (
                <div className="max-w-lg ml-auto bg-blue-600 rounded-2xl rounded-tr-sm px-4 py-3 text-sm text-white shadow-sm">
                  {msg.text}
                </div>
              ) : (
                <div className="max-w-lg bg-white rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-gray-700 shadow-sm">
                  {msg.text}
                  {msg.sources && msg.sources.length > 0 && (
                    <details className="mt-2">
                      <summary className="text-xs text-gray-500 cursor-pointer">Sources ({msg.sources.length})</summary>
                      {msg.sources.map((s, j) => (
                        <p key={j} className="text-xs text-gray-500 mt-1">{s.filename}, page {s.page}</p>
                      ))}
                    </details>
                  )}
                </div>
              )}
            </div>
          ))}
          {asking && <div className="max-w-lg bg-white rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-gray-400 shadow-sm">Thinking...</div>}
        </div>

        <div className="border-t border-gray-200 p-4 bg-white">
          <div className="flex gap-3">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
              placeholder="Ask a question..."
              className="flex-1 border border-gray-200 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={handleAsk}
              disabled={!question.trim() || asking}
              className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:bg-gray-300 transition"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App