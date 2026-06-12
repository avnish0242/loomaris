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

  useEffect(() => {
    getMe()
      .then((me) => {
        if (!me.user.has_claude_key) {
          setShowKeyModal(true);
        } else if (!me.user.has_cloud_account) {
          // Don't auto-prompt cloud modal — let user discover via Sidebar
          // but keep the state so Sidebar "Connect AWS" button can open it
        }
      })
      .catch(() => {});
  }, []);

  const handleKeyModalDone = () => {
    setShowKeyModal(false);
  };

  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden" style={{ background: 'var(--void)' }}>
        <Sidebar onOpenCloudConnect={() => setShowCloudModal(true)} />
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden">{children}</main>
      </div>

      {showKeyModal && (
        <ApiKeyModal
          onSaved={handleKeyModalDone}
          onDismiss={handleKeyModalDone}
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
