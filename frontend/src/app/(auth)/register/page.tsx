"use client";

/**
 * Create an account. FR-1 and FR-3.
 *
 * Native language is asked for here rather than being left to a settings page nobody
 * visits, because m8 needs it to say anything useful the first time somebody reads a
 * passage aloud: which English sounds a speaker's first language does not have is the
 * difference between "your /v/ is weak" and a prediction the system could have made
 * before hearing a word. A column full of defaults would be the same as not having it.
 *
 * The self-assessed band is optional and says so. It is a starting point for
 * recommendations, not a claim the system will hold anybody to — it is replaced by
 * measurement as soon as there is any.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/hooks/useAuth";
import { CEFR_BANDS, NATIVE_LANGUAGES } from "@/lib/auth";

/** Mirrors `Password` in api/models/auth.py. Stated to the user rather than discovered
 *  by them through a 422. */
const MIN_PASSWORD_LENGTH = 8;

export default function RegisterPage() {
  const router = useRouter();
  const { signUp, error, pending } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nativeLanguage, setNativeLanguage] = useState("es");
  const [band, setBand] = useState<string>("");

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const profile = await signUp({
      email,
      password,
      native_language: nativeLanguage,
      // The API distinguishes absent from null, and an unanswered optional question is
      // absent. Sending "" would be a 422 on a field the person chose not to fill in.
      ...(band ? { cefr_self_assessed: band } : {}),
    });
    if (profile) {
      // The catalogue, not the home page. Somebody who has just created an account
      // came here to practise, and the home page is a stack diagnostic.
      router.push("/scenarios");
      router.refresh();
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-2xl">Create an account</CardTitle>
        <CardDescription>
          Your first language shapes which sounds SpeakLab listens for.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <p className="text-muted-foreground text-xs">
              At least {MIN_PASSWORD_LENGTH} characters.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="native-language">First language</Label>
            <Select value={nativeLanguage} onValueChange={setNativeLanguage}>
              <SelectTrigger id="native-language" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {NATIVE_LANGUAGES.map((language) => (
                  <SelectItem key={language.value} value={language.value}>
                    {language.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="band">Current level</Label>
            <Select value={band} onValueChange={setBand}>
              <SelectTrigger id="band" className="w-full">
                <SelectValue placeholder="Optional" />
              </SelectTrigger>
              <SelectContent>
                {CEFR_BANDS.map((value) => (
                  <SelectItem key={value} value={value}>
                    {value}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-muted-foreground text-xs">
              A starting point only — SpeakLab replaces it with what it measures.
            </p>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <Button type="submit" disabled={pending} className="mt-2">
            {pending ? "Creating account…" : "Create account"}
          </Button>
        </form>

        <p className="text-muted-foreground mt-6 text-center text-sm">
          Already have an account?{" "}
          <Link href="/login" className="text-foreground underline underline-offset-4">
            Sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
