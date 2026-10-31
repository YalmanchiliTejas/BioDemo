import Link from "next/link";
import CaseStudies from "@/components/process/CaseStudies";
import { BrandMark } from "@/components/shell/BrandMark";
export default function StudiesPage() { return <main className="px-5 py-6 sm:px-10"><header className="mx-auto mb-12 flex max-w-[1200px] items-center justify-between"><BrandMark href="/"/><Link href="/">Back to home</Link></header><CaseStudies/></main>; }
