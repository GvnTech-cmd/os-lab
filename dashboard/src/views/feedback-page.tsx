import { BugIcon, ChatCircleTextIcon, LightbulbIcon, ShieldWarningIcon } from "@phosphor-icons/react";
import { AppShell, REPO_URL } from "../shell/app-shell";
import { TopBar } from "../shell/top-bar";
import { PageHead } from "../components/ui";

const options = [
  {
    title: "Report an issue",
    description: "Tell us what broke, which lab or page you used, and how to reproduce it.",
    icon: BugIcon,
    href: `${REPO_URL}/issues/new?template=bug_report.yml`
  },
  {
    title: "Request a feature",
    description: "Suggest a new capability or an improvement to an existing workflow.",
    icon: LightbulbIcon,
    href: `${REPO_URL}/issues/new?template=feature_request.yml`
  },
  {
    title: "Share feedback or ask a question",
    description: "Start a discussion about your experience, setup, or idea.",
    icon: ChatCircleTextIcon,
    href: `${REPO_URL}/discussions/new/choose`
  },
  {
    title: "Report a security concern",
    description: "Send a vulnerability report privately through the repository security page.",
    icon: ShieldWarningIcon,
    href: `${REPO_URL}/security/advisories/new`
  }
];

export default function FeedbackPage() {
  return (
    <AppShell activeId="feedback">
      <TopBar title="Feedback" icon={<ChatCircleTextIcon size={20} weight="duotone" />} />
      <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-4 sm:p-6">
        <PageHead icon={<ChatCircleTextIcon size={22} />} title="Feedback" description="Report a problem, request a feature, or tell us what could work better." />
        <div className="grid gap-4 sm:grid-cols-2">
          {options.map(({ title, description, icon: Icon, href }) => (
            <a key={title} className="iux-card gap-3 p-5 transition-colors hover:border-[#f36c21] focus-visible:outline-2 focus-visible:outline-[#f36c21]" href={href} target="_blank" rel="noopener noreferrer">
              <Icon size={24} className="text-[#f36c21]" />
              <h2 className="text-base font-semibold">{title}</h2>
              <p className="text-sm leading-relaxed text-(--iux-muted-foreground)">{description}</p>
            </a>
          ))}
        </div>
      </main>
    </AppShell>
  );
}
