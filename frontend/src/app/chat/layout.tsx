'use client';

import { useEffect, useState } from 'react';
import AuthGuard from '@/components/AuthGuard';
import Sidebar from '@/components/Sidebar';
import ApiKeyModal from '@/components/ApiKeyModal';
import CloudConnectModal from '@/components/CloudConnectModal';
import { getMe } from '@/lib/api';

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [showCloudModal, setShowCloudModal] = useState(false);
  const [orgName, setOrgName] = useState<string | undefined>();
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    getMe()
      .then((me) => {
        const admin = me.user.is_superadmin || me.role === 'owner' || me.role === 'admin';
        setIsAdmin(admin);
        setOrgName(me.org?.name);
        if (!me.user.has_claude_key) {
          setShowKeyModal(true);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden" style={{ background: 'var(--void)' }}>
        <Sidebar onOpenCloudConnect={() => setShowCloudModal(true)} />
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden">{children}</main>
      </div>

      {showKeyModal && (
        <ApiKeyModal
          onSaved={() => setShowKeyModal(false)}
          onDismiss={() => setShowKeyModal(false)}
          orgName={orgName}
          isAdmin={isAdmin}
        />
      )}

      {showCloudModal && (
        <CloudConnectModal
          onConnected={() => setShowCloudModal(false)}
          onDismiss={() => setShowCloudModal(false)}
        />
      )}
    </AuthGuard>
  );
}
