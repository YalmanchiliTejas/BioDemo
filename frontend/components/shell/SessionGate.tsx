'use client';
import { useEffect } from 'react';
import { redirectToSignIn, useSession } from '@/lib/auth';
export function SessionGate({ children }: {
    children: React.ReactNode;
}) {
    const { user, loading, mode } = useSession();
    useEffect(() => { if (!loading && !user && mode === 'supabase')
        redirectToSignIn('required'); }, [user, loading, mode]);
    if (mode === 'supabase' && (loading || !user))
        return <div className="p-10" role="status">Checking your session…</div>;
    return <>{children}</>;
}
