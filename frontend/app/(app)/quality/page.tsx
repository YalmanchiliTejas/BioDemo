'use client';
import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { QualityWorkspacePage } from '@/components/quality/QualityWorkspace';
import QualityDemo from '@/components/quality/QualityDemo';
function QualityRoute() { return useSearchParams().get('demo') === '1' ? <QualityDemo /> : <QualityWorkspacePage />; }
export default function QualityPage() { return <Suspense fallback={<p className="p-8">Opening Quality…</p>}><QualityRoute /></Suspense>; }
