function AppShell({
  brandTagline = "Blood coordination platform",
  nav,
  activePath,
  onNavigate,
  user,
  headerExtras,
  sidebarFooter,
  onSignOut,
  verificationNotice,
  children
}) {
  return <div className="bl-app"><header className="bl-app__header"><a
    className="bl-app__brand"
    href="/"
    onClick={(event) => {
      event.preventDefault();
      onNavigate("/");
    }}
  ><span className="bl-app__logo">B</span><span><span className="bl-app__brand-name">BloodLink</span><br /><span className="bl-app__brand-tag">{brandTagline}</span></span></a><span className="bl-spacer" />{headerExtras}{user ? <div className="bl-header-user"><span className="bl-avatar" aria-hidden="true">{user.initials}</span><span><span style={{ fontWeight: 600 }}>{user.name}</span><br /><span style={{ fontSize: "var(--bl-font-size-xs)", opacity: 0.75 }}>{user.role.replace(/_/g, " ")}{user.organization ? ` \xB7 ${user.organization}` : ""}</span></span>{onSignOut ? <button type="button" className="bl-bell" title="Sign out" onClick={onSignOut}>
                ⏻
              </button> : null}</div> : null}</header><div className="bl-app__body"><nav className="bl-app__sidebar" aria-label="Main navigation">{nav.map((group) => <div className="bl-app__nav-group" key={group.label}><div className="bl-app__nav-label">{group.label}</div>{group.links.map((link) => {
    const active = activePath === link.to || activePath.startsWith(`${link.to}/`);
    return <a
      key={link.to}
      href={link.to}
      className={`bl-app__nav-link${active ? " bl-app__nav-link--active" : ""}`}
      onClick={(event) => {
        event.preventDefault();
        onNavigate(link.to);
      }}
    >{link.icon ? <span aria-hidden="true">{link.icon}</span> : null}<span>{link.label}</span>{link.badge ? <span className="bl-spacer" /> : null}{link.badge ? <span className="bl-badge bl-badge--danger">{link.badge}</span> : null}</a>;
  })}</div>)}{sidebarFooter ? <div className="bl-app__nav-group">{sidebarFooter}</div> : null}</nav><main className="bl-app__main"><div className="bl-app__container">{verificationNotice}{children}</div></main></div></div>;
}
export {
  AppShell
};
