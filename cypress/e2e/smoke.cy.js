/// <reference types="cypress" />

function normalizeText(s = '') { return String(s).replace(/\s+/g, ' ').trim(); }
function isVisible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  const style = window.getComputedStyle(el);
  return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
}
function findClickableAncestor(el) {
  let cur = el;
  while (cur && cur !== document.body) {
    const role = (cur.getAttribute && cur.getAttribute('role')) || '';
    if (cur.tagName === 'A' || cur.tagName === 'BUTTON' || /button|link/i.test(role) || cur.hasAttribute('onclick') || cur.tabIndex >= 0) {
      return cur;
    }
    cur = cur.parentElement;
  }
  return el;
}
function clickFirstVisibleByText(re, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  const tryOnce = () => {
    return cy.get('body', { includeShadowDom: true }).then(($body) => {
      const root = $body[0];
      const nodes = Array.from(root.querySelectorAll('*'));
      const match = nodes.find((el) => {
        if (!isVisible(el)) return false;
        const txt = normalizeText(el.innerText || el.textContent || '');
        return re.test(txt);
      });
      if (match) {
        const clickable = findClickableAncestor(match);
        cy.wrap(clickable).scrollIntoView().click({ force: true });
        return;
      }
      if (Date.now() < deadline) return cy.wait(750).then(tryOnce);
      throw new Error(`Élément avec texte ${re} introuvable ou non cliquable`);
    });
  };
  return tryOnce();
}

function ensureAppMounted() {
  cy.ensureAppMounted?.() || (function () {
    cy.document().its('readyState', { timeout: 60000 }).should('eq', 'complete');
    const CONTAINER_SEL = '#portal, #root, main, [data-testid="app"], [data-app], [data-glide-container]';
    cy.get('body', { includeShadowDom: true, timeout: 20000 }).then(($b) => {
      const has = $b.find(CONTAINER_SEL).length > 0;
      if (!has) {
        cy.visit('/?fresh=' + Date.now());
        cy.document().its('readyState', { timeout: 60000 }).should('eq', 'complete');
        cy.get(CONTAINER_SEL, { includeShadowDom: true, timeout: 30000 }).should('exist');
      }
    });
  })();
}

describe('Sport Cov (PROD) - smoke', () => {
  beforeEach(() => {
    cy.loginOtp();                 // restaure ou reconnecte (validate())
    cy.visit('/?e2e=' + Date.now());
    ensureAppMounted();

    // Garde-fou "écran login" — SANS CSS4 `[ i ]`
    cy.get('body', { includeShadowDom: true }).then(($b) => {
      const emailInputs = Array.from($b[0].querySelectorAll('input[type="email"], input[placeholder], input[data-testid]'));
      const hasLogin = emailInputs.some((n) => {
        const ph  = (n.getAttribute('placeholder') || '').toLowerCase();
        const id  = (n.getAttribute('id') || '').toLowerCase();
        const nm  = (n.getAttribute('name') || '').toLowerCase();
        const dt  = (n.getAttribute('data-testid') || '').toLowerCase();
        return n.type === 'email' || /mail|e-?mail|courriel|adresse/.test(ph + ' ' + id + ' ' + nm + ' ' + dt);
      });
      if (hasLogin) {
        cy.log('[auth] écran de connexion détecté — relance forcée de la session');
        cy.window().then((win) => { try { win.localStorage.clear(); } catch (_) {} });
        cy.loginOtp();               // re-crée la session
        cy.visit('/?e2e=' + Date.now());
        ensureAppMounted();
      }
    });
  });

  it('ouvre l’équipe, va au Tableau de bord et vérifie le lien Google Maps', () => {
    // Ouvrir l’équipe
    const TEAM_RE = /seniors?\s*2[\s_-]*amboise/i;
    clickFirstVisibleByText(TEAM_RE, 30000);

    // Aller onglet "Tableau de bord" (gère "Plus")
    cy.get('body', { includeShadowDom: true }).then(($body) => {
      const all = Array.from($body[0].querySelectorAll('a,button,[role="tab"],[role="menuitem"],[role="button"]'))
        .filter((el) => isVisible(el));

      const direct = all.find((el) => {
        const txt   = normalizeText(el.innerText || el.textContent || '');
        const aria  = normalizeText(el.getAttribute('aria-label') || '');
        const title = normalizeText(el.getAttribute('title') || '');
        return /tableau\s*de\s*bord/i.test(`${txt} ${aria} ${title}`);
      });

      if (direct) {
        cy.wrap(direct).click({ force: true });
      } else {
        const moreBtn = all.find((el) => /^plus\b/i.test(normalizeText(el.innerText || el.textContent || '')));
        if (moreBtn) cy.wrap(moreBtn).click({ force: true });
        else cy.contains('button, [role="button"], a', /^plus\b/i, { includeShadowDom: true, timeout: 15000 }).click({ force: true });

        cy.contains('[role="menuitem"], a, button', /tableau\s*de\s*bord/i, { includeShadowDom: true, timeout: 15000 }).click({ force: true });
      }
    });

    // ---- Vérifications Google Maps ----
    // 1) Vérif générique présence + format (web ou deep-link/shortlink)
    cy.assertGoogleMapsLink({ timeout: 30000 });

    // 2) Vérif “deep” optionnelle si une URL attendue est fournie via l’ENV
    //    (ex: E2E_EXPECTED_MAPS_URL="https://www.google.com/maps/dir/?api=1&origin=...&destination=...&waypoints=...|...")
    const expected = Cypress.env('E2E_EXPECTED_MAPS_URL');
    if (expected) {
      cy.assertGoogleMapsDeepLink(expected, { timeout: 30000 })
        .then(() => cy.log('[Maps] deep-link conforme'));
    }
  });
});
