'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { setToken, getToken } from '@/lib/auth';

// Handles redirect from backend after Google OAuth in dev mode.
// Backend redirects to /#token=<jwt> (root), which is handled in app/page.tsx.
// This route is a fallback if the backend is configured to redirect here instead.
export default function AuthCallback() {
  const router = useRouter();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const hash = new URLSearchParams(window.location.hash.slice(1));
    const token = params.get('token') ?? hash.get('token');

    if (token) {
      setToken(token);
    }

    if (getToken()) {
      router.replace('/chat');
    } else {
      router.replace('/login');
    }
  }, [router]);

  return (
    <div className="h-screen flex items-center justify-center bg-surface-base">
      <div className="w-5 h-5 rounded-full border-2 border-brand border-t-transparent animate-spin" />
    </div>
  );
}
