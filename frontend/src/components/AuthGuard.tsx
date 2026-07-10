'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { consumeAuthHash, getToken, setToken } from '@/lib/auth';
import { getMe } from '@/lib/api';

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const router = useRouter();

  useEffect(() => {
    // 1. Check for fresh OAuth redirect (token in hash fragment)
    const auth = consumeAuthHash();
    if (auth) {
      setToken(auth.token);
      router.replace(auth.next);
      return;
    }

    // 2. Existing session — verify it and check membership status
    const token = getToken();
    if (!token) {
      router.replace('/login');
      return;
    }

    getMe()
      .then((me) => {
        if (me.membership_status === 'pending') {
          router.replace('/waiting');
        } else if (me.membership_status === 'none') {
          if (me.user.is_superadmin) {
            router.replace('/admin');
          } else {
            router.replace('/onboarding');
          }
        } else {
          setReady(true);
        }
      })
      .catch(() => {
        // Token expired or invalid
        router.replace('/login');
      });
  }, [router]);

  if (!ready) {
    return (
      <div className="h-screen flex items-center justify-center" style={{ background: 'var(--void)' }}>
        <div className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: 'rgba(129,140,248,0.3)', borderTopColor: '#818cf8' }} />
      </div>
    );
  }

  return <>{children}</>;
}
