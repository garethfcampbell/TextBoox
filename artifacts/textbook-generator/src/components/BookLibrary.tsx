import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';

interface LibraryBook {
  id: number;
  title: string;
  topic: string;
  createdAt: string;
}

const FORMATS = ['html', 'pdf', 'epub'] as const;

export function BookLibrary() {
  const [books, setBooks] = useState<LibraryBook[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/textbook/library')
      .then((r) => r.json())
      .then((data) => {
        setBooks(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return null;
  if (books.length === 0) return (
    <p className="text-sm text-muted-foreground">No textbooks generated yet.</p>
  );

  return (
    <div className="flex flex-col gap-3">
      {books.map((book) => (
        <div
          key={book.id}
          className="bg-white border border-border rounded-xl p-4 shadow-sm"
        >
          <h3 className="font-display font-semibold text-sm text-primary leading-snug mb-2">
            {book.title}
          </h3>
          <div className="flex gap-2 flex-wrap">
            {FORMATS.map((fmt) => (
              <a
                key={fmt}
                href={`/api/textbook/library/${book.id}/download/${fmt}`}
                download
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-secondary text-primary text-xs font-semibold uppercase tracking-wide hover:bg-accent/10 hover:text-accent transition-colors"
              >
                <Download className="w-3 h-3" />
                {fmt}
              </a>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
