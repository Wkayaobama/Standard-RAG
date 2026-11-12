import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from 'react';
import {
  Upload,
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Download,
  MessageSquare,
  Send,
  Layers,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

type PdfRow = {
  id: string;
  filename: string;
  status: 'pending' | 'running' | 'done' | 'error';
  error: string | null;
  created_at: string;
};

type Citation = { pdf_id: string; section_path: string };
type ChatMessage = { role: 'user' | 'assistant'; content: string; citations?: Citation[] };

export default function App() {
  const [pdfs, setPdfs] = useState<PdfRow[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [corpusBuilding, setCorpusBuilding] = useState(false);
  const [corpusInfo, setCorpusInfo] = useState<{ bytes: number; pdfs: number } | null>(null);

  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatting, setChatting] = useState(false);

  const refreshPdfs = useCallback(async () => {
    try {
      const res = await fetch('/api/pdfs');
      if (!res.ok) return;
      setPdfs(await res.json());
    } catch {
      /* ignore transient */
    }
  }, []);

  useEffect(() => {
    refreshPdfs();
    const iv = setInterval(refreshPdfs, 1500);
    return () => clearInterval(iv);
  }, [refreshPdfs]);

  const uploadFiles = async (files: File[]) => {
    const pdfs = files.filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (pdfs.length === 0) return;
    setUploading(true);
    try {
      const form = new FormData();
      for (const f of pdfs) form.append('files', f);
      const res = await fetch('/api/pdfs', { method: 'POST', body: form });
      if (!res.ok) throw new Error(await res.text());
      await refreshPdfs();
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    uploadFiles(Array.from(e.dataTransfer.files));
  };

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) uploadFiles(Array.from(e.target.files));
  };

  const buildCorpus = async () => {
    setCorpusBuilding(true);
    try {
      const res = await fetch('/api/corpus/build', { method: 'POST' });
      if (!res.ok) throw new Error(await res.text());
      setCorpusInfo(await res.json());
    } finally {
      setCorpusBuilding(false);
    }
  };

  const sendChat = async () => {
    const q = question.trim();
    if (!q || chatting) return;
    setQuestion('');
    const nextMessages = [...messages, { role: 'user' as const, content: q }];
    setMessages(nextMessages);
    setChatting(true);
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: q,
          history: messages.map(m => ({ role: m.role, content: m.content })),
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setMessages([
        ...nextMessages,
        { role: 'assistant', content: data.answer, citations: data.citations },
      ]);
    } catch (err) {
      setMessages([
        ...nextMessages,
        { role: 'assistant', content: `Error: ${err}` },
      ]);
    } finally {
      setChatting(false);
    }
  };

  const doneCount = pdfs.filter(p => p.status === 'done').length;
  const anyRunning = pdfs.some(p => p.status === 'running' || p.status === 'pending');

  return (
    <div className="relative min-h-screen bg-background">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[420px] bg-gradient-to-b from-primary/10 via-background to-background"
      />
      <main className="container mx-auto max-w-3xl px-6 py-14 space-y-6">
        <div className="text-center space-y-2">
          <Badge variant="secondary" className="gap-1.5">
            <Layers className="h-3 w-3" /> Standard-RAG
          </Badge>
          <h1 className="text-4xl font-bold tracking-tight bg-gradient-to-br from-foreground to-foreground/60 bg-clip-text text-transparent">
            PDFs to Markdown, chat with the corpus
          </h1>
          <p className="text-muted-foreground text-sm max-w-md mx-auto">
            Upload PDFs, let the backend convert and consolidate them, then query
            the result through Claude.
          </p>
        </div>

        <Card>
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Upload className="h-4 w-4 text-primary" /> Upload PDFs
            </CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            <div
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                'flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors',
                dragging
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/40 hover:bg-muted/30',
              )}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                multiple
                className="hidden"
                onChange={onPick}
              />
              {uploading ? (
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
              ) : (
                <Upload className="h-6 w-6 text-muted-foreground" />
              )}
              <p className="text-sm font-medium">Drop PDFs here or click to browse</p>
              <p className="text-xs text-muted-foreground">
                Multi-select OK — each file converts in parallel.
              </p>
            </div>
          </CardContent>
        </Card>

        {pdfs.length > 0 && (
          <Card>
            <CardHeader className="pb-2 pt-4 px-5">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <FileText className="h-4 w-4 text-primary" />
                PDFs {anyRunning && <span className="text-primary">· processing…</span>}
              </CardTitle>
            </CardHeader>
            <CardContent className="px-5 pb-5 space-y-2">
              {pdfs.map(p => (
                <div
                  key={p.id}
                  className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2"
                >
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{p.filename}</p>
                    {p.error && (
                      <p className="truncate text-xs text-destructive">{p.error}</p>
                    )}
                  </div>
                  {p.status === 'done' && (
                    <Badge className="gap-1 text-green-700 bg-green-100 border-green-200 dark:bg-green-950 dark:text-green-400 dark:border-green-900">
                      <CheckCircle2 className="h-3 w-3" /> done
                    </Badge>
                  )}
                  {(p.status === 'pending' || p.status === 'running') && (
                    <Badge variant="secondary" className="gap-1">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      {p.status}
                    </Badge>
                  )}
                  {p.status === 'error' && (
                    <Badge variant="destructive" className="gap-1">
                      <AlertCircle className="h-3 w-3" /> error
                    </Badge>
                  )}
                  {p.status === 'done' && (
                    <a
                      href={`/api/pdfs/${p.id}/markdown`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <Button variant="outline" size="sm" className="h-7 gap-1 text-xs">
                        <Download className="h-3 w-3" /> .md
                      </Button>
                    </a>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {doneCount > 0 && (
          <Card>
            <CardHeader className="pb-2 pt-4 px-5">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Layers className="h-4 w-4 text-primary" /> Consolidated corpus
              </CardTitle>
            </CardHeader>
            <CardContent className="px-5 pb-5 space-y-3">
              <p className="text-xs text-muted-foreground">
                Consolidate all {doneCount} converted PDF{doneCount !== 1 ? 's' : ''} into a single{' '}
                <code>corpus.md</code>.
              </p>
              <div className="flex items-center gap-3">
                <Button
                  onClick={buildCorpus}
                  disabled={corpusBuilding}
                  size="sm"
                  className="gap-1.5"
                >
                  {corpusBuilding ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> Building…</>
                  ) : (
                    <><Layers className="h-4 w-4" /> Build corpus</>
                  )}
                </Button>
                {corpusInfo && (
                  <>
                    <span className="text-xs text-muted-foreground">
                      {corpusInfo.pdfs} PDF{corpusInfo.pdfs !== 1 ? 's' : ''} · {Math.round(corpusInfo.bytes / 1024)} KB
                    </span>
                    <a href="/api/corpus" download>
                      <Button variant="outline" size="sm" className="gap-1.5">
                        <Download className="h-4 w-4" /> Download
                      </Button>
                    </a>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {doneCount > 0 && (
          <Card>
            <CardHeader className="pb-2 pt-4 px-5">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-primary" /> Assistant
              </CardTitle>
            </CardHeader>
            <CardContent className="px-5 pb-5 space-y-3">
              <div className="space-y-2 max-h-[400px] overflow-y-auto">
                {messages.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Ask a question about anything in the uploaded PDFs.
                  </p>
                ) : (
                  messages.map((m, i) => (
                    <div
                      key={i}
                      className={cn(
                        'rounded-lg px-3 py-2 text-sm',
                        m.role === 'user'
                          ? 'bg-primary/10 ml-8'
                          : 'bg-muted mr-8',
                      )}
                    >
                      <p className="whitespace-pre-wrap">{m.content}</p>
                      {m.citations && m.citations.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {m.citations.map((c, j) => (
                            <Badge key={j} variant="outline" className="text-[10px] font-normal">
                              {c.section_path || '(root)'}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
              <div className="flex gap-2">
                <Input
                  value={question}
                  onChange={e => setQuestion(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && sendChat()}
                  placeholder="Ask a question…"
                  disabled={chatting}
                  className="flex-1"
                />
                <Button onClick={sendChat} disabled={chatting || !question.trim()} size="sm" className="gap-1.5">
                  {chatting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <><Send className="h-4 w-4" /> Send</>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
