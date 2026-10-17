export const metadata = { title: 'Privacy Policy — SocialGrow AI' }

const S = ({ title, children }) => (
  <section className="mt-6">
    <h2 className="text-lg font-bold">{title}</h2>
    <div className="mt-2 space-y-2 text-sm leading-relaxed text-muted-foreground">{children}</div>
  </section>
)

export default function Privacy() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <a href="/" className="text-sm text-primary">← SocialGrow AI</a>
      <h1 className="mt-4 text-2xl font-extrabold">Privacy Policy</h1>
      <p className="mt-1 text-xs text-muted-foreground">Last updated: 16 October 2026</p>
      <S title="Who we are">
        <p>SocialGrow AI is a social media analytics and reporting tool for agencies and businesses. Contact: testdigiquest@gmail.com</p>
      </S>
      <S title="What we collect">
        <p>Account data you give us: name, email, agency name, phone number and an encrypted (hashed) password.</p>
        <p>When you or your client connect Facebook, Instagram or YouTube by logging in, we receive read-only access tokens and read
          public profile and performance data of the Pages, Instagram Business accounts and YouTube channels you choose: name, username,
          follower/subscriber counts, posts/videos and their likes, comments, shares and views.</p>
        <p>We do not receive or store your Facebook or Google password. We never delete anything or send messages. For YouTube channels
          connected with Google, the agency managing your channel can reply to comments from inside SocialGrow — only when a team member
          writes and sends that reply; nothing is posted automatically.</p>
      </S>
      <S title="How we use it">
        <p>Only to show analytics, growth charts, AI insights and reports inside your SocialGrow workspace, and to send service emails
          (password reset, trial and billing reminders). We do not sell or share your data with advertisers.</p>
        <p>YouTube data is accessed through YouTube API Services; by connecting YouTube you also agree to the
          <a className="text-primary" href="https://www.youtube.com/t/terms"> YouTube Terms of Service</a> and
          <a className="text-primary" href="https://policies.google.com/privacy"> Google Privacy Policy</a>.
          SocialGrow AI&apos;s use of information received from Google APIs adheres to the Google API Services User Data Policy, including the Limited Use requirements.</p>
      </S>
      <S title="Storage and security">
        <p>Data is stored in an encrypted PostgreSQL database. Tokens are kept on our server only and are never shown in the browser.
          Each workspace&apos;s data is isolated from other workspaces.</p>
      </S>
      <S title="Your choices and data deletion">
        <p>You can disconnect any account in Settings or Social Accounts at any time; its stored data is deleted. You can also remove
          SocialGrow&apos;s access from your Facebook settings (Business Integrations) or Google account (Third-party access).</p>
        <p>To delete your whole account and all data, email testdigiquest@gmail.com from your registered email — we delete it within 30 days.</p>
      </S>
      <S title="Changes">
        <p>We may update this policy; the date above shows the latest version.</p>
      </S>
    </main>
  )
}
