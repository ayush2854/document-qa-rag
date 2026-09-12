import { useState } from 'react'

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState<any>(null)

  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [answer, setAnswer] = useState<any>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
    }
  }

  const handleUpload = async () => {
    if (!file) return

    setUploading(true)
    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch('http://127.0.0.1:8000/upload', {
        method: 'POST',
        body: formData,
      })
      const data = await response.json()
      setUploadResult(data)
    } catch (error) {
      console.error('Upload failed:', error)
      setUploadResult({ error: 'Upload failed. Check console.' })
    } finally {
      setUploading(false)
    }
  }

  const handleAsk = async () => {
    if (!question.trim()) return

    setAsking(true)
    try {
      const response = await fetch('http://127.0.0.1:8000/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: question }),
      })
      const data = await response.json()
      setAnswer(data)
    } catch (error) {
      console.error('Question failed:', error)
      setAnswer({ error: 'Failed to get answer. Check console.' })
    } finally {
      setAsking(false)
    }
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '600px', margin: '0 auto' }}>
      <h1>Document Q&A</h1>

      <div style={{ marginBottom: '1.5rem' }}>
        <h2>1. Upload a PDF</h2>
        <input type="file" accept=".pdf" onChange={handleFileChange} />
        <button onClick={handleUpload} disabled={!file || uploading} style={{ marginLeft: '1rem' }}>
          {uploading ? 'Uploading...' : 'Upload'}
        </button>

        {uploadResult && (
          <p>
            {uploadResult.error
              ? uploadResult.error
              : `Uploaded "${uploadResult.filename}" — ${uploadResult.num_chunks} chunks stored.`}
          </p>
        )}
      </div>

      <div>
        <h2>2. Ask a question</h2>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What do you want to know?"
          style={{ width: '70%', padding: '0.5rem' }}
        />
        <button onClick={handleAsk} disabled={!question.trim() || asking} style={{ marginLeft: '1rem' }}>
          {asking ? 'Thinking...' : 'Ask'}
        </button>
        {answer && (
          <div style={{ marginTop: '1rem' }}>
            {answer.error ? (
              <p>{answer.error}</p>
            ) : (
              <>
                <p><strong>Answer:</strong> {answer.answer}</p>
                <details>
                  <summary>Chunks used ({answer.chunks_used.length})</summary>
                  {answer.chunks_used.map((chunk: string, i: number) => (
                    <p key={i} style={{ fontSize: '0.85rem', color: '#555' }}>{chunk}</p>
                  ))}
                </details>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default App