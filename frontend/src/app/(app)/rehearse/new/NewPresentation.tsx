"use client";

/**
 * The script, the split it would get, and the chance to move a boundary before saving.
 *
 * **Preview, then save, rather than save and re-split.** The sections are what every take
 * is compared against, so a talk saved in the wrong pieces is a talk rehearsed in the
 * wrong pieces. The preview is one request, it comes back in milliseconds, and it is the
 * only moment where moving a boundary costs nothing.
 *
 * **Joining, not editing.** The only change offered here is joining a section to the one
 * before it. Editing the words in this box would let the sections say something the saved
 * script does not, and the server refuses that — the words have to add up. Changing the
 * talk means changing the script and previewing again.
 *
 * The words that cannot be scored are named per section as soon as they are known, with
 * what to do about them, because respelling a figure is a change to the script and this is
 * the last moment before it is saved.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Merge } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  type SplitPreview,
  createPresentation,
  previewPresentation,
} from "@/lib/api";

/** What a script looks like: spoken sentences, a blank line where a part ends. */
const PLACEHOLDER = `Good morning. Thank you for coming. Today I want to walk you through what we shipped this quarter, and what it cost us.

First, the numbers. Revenue grew twelve percent, which is ahead of the plan we set in January.`;

interface Piece {
  body: string;
  unscorable: string[];
}

export function NewPresentation() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [script, setScript] = useState("");
  const [preview, setPreview] = useState<SplitPreview | null>(null);
  // The sections as they stand, each carrying the words that cannot be scored in it.
  // Kept together rather than as two lists, because joining two sections has to join
  // their words as well — the names are what the reader is told to go and respell.
  const [pieces, setPieces] = useState<Piece[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function look() {
    setError(null);
    setBusy(true);
    try {
      const split = await previewPresentation({ title: title || "Untitled", script });
      setPreview(split);
      setPieces(
        split.sections.map((body, index) => ({
          body,
          unscorable: split.unscorable[index] ?? [],
        })),
      );
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "That script could not be read.");
    } finally {
      setBusy(false);
    }
  }

  function joinToPrevious(index: number) {
    setPieces((current) =>
      current.reduce<Piece[]>((kept, piece, i) => {
        const previous = kept[kept.length - 1];
        if (i === index && previous) {
          kept[kept.length - 1] = {
            body: `${previous.body} ${piece.body}`,
            unscorable: [...previous.unscorable, ...piece.unscorable],
          };
        } else {
          kept.push(piece);
        }
        return kept;
      }, []),
    );
  }

  async function save() {
    setError(null);
    setBusy(true);
    try {
      const saved = await createPresentation({
        title: title || "Untitled",
        script,
        sections: pieces.map((piece) => piece.body),
      });
      router.push(`/rehearse/${saved.id}`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "That script could not be saved.");
      setBusy(false);
    }
  }

  const words = script.trim() ? script.trim().split(/\s+/).length : 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Label htmlFor="title">What is the talk called?</Label>
        <Input
          id="title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Quarterly update"
          className="max-w-md"
        />
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="script">The script</Label>
        <Textarea
          id="script"
          value={script}
          onChange={(event) => {
            setScript(event.target.value);
            setPreview(null);
          }}
          rows={14}
          placeholder={PLACEHOLDER}
        />
        <p className="text-xs text-muted-foreground">
          <span className="tabular-nums">{words} words</span>. Line breaks inside a part are
          wrapping; a blank line starts a new one. Figures are best written the way you say
          them — &ldquo;twelve percent&rdquo;, &ldquo;twenty twenty-six&rdquo; — and anything
          that cannot be turned into sounds is named under its section below.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" onClick={() => void look()} disabled={busy || words === 0}>
          {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
          See the split
        </Button>
        {preview && (
          <Button type="button" variant="default" onClick={() => void save()} disabled={busy}>
            Save the script
          </Button>
        )}
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {preview && (
        <section className="flex flex-col gap-4" aria-labelledby="split">
          <h2 id="split" className="text-lg font-semibold tracking-tight">
            {pieces.length === 1 ? "One section" : `${pieces.length} sections`}
          </h2>

          {preview.pron === "unavailable" && (
            <p className="text-sm text-muted-foreground">
              The pronunciation scorer is not running, so which words can be scored sound by
              sound has not been checked. Everything else works as it does with it on.
            </p>
          )}

          <ul className="flex flex-col gap-3">
            {pieces.map((piece, index) => (
              <li key={index}>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between gap-4">
                    <CardTitle className="text-sm tabular-nums text-muted-foreground">
                      Section {index + 1} · {piece.body.trim().split(/\s+/).length} words
                    </CardTitle>
                    {index > 0 && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => joinToPrevious(index)}
                        aria-label={`Join section ${index + 1} to the one before it`}
                      >
                        <Merge aria-hidden="true" />
                        Join to the one above
                      </Button>
                    )}
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2">
                    <p className="text-sm leading-relaxed">{piece.body}</p>
                    {piece.unscorable.length > 0 && (
                      <p className="text-sm text-muted-foreground">
                        These cannot be turned into sounds:{" "}
                        <span className="font-medium">{piece.unscorable.join(", ")}</span>
                        . Everything else here still works — to have the sounds scored too,
                        write them the way you say them (&ldquo;twenty twenty-six&rdquo;,
                        &ldquo;A P I&rdquo;) and look again.
                      </p>
                    )}
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
