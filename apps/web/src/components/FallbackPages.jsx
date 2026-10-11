import { Card } from "@bloodlink/ui";
function NotFoundPage() {
  return <Card title="Page not found"><p className="bl-muted">
        That screen does not exist. Use the navigation on the left to get back to your workspace.
      </p></Card>;
}
function UnauthorizedPage() {
  return <Card title="Not available for your role"><p className="bl-muted">
        Your account role cannot open this screen. Authorization is enforced by the API — the web
        client only reflects it.
      </p></Card>;
}
export {
  NotFoundPage,
  UnauthorizedPage
};
