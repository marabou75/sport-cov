// cypress/support/e2e.js

/// <reference types="cypress" />

/**
 * Login par e-mail + OTP sur l’app Glide (prod).
 * - Récupère le PIN via IMAP (cy.task('getOtpGmail')).
 * - Détecte/remplit tous les types d’UI OTP.
 * - Date `since` APRÈS l’ACK de sendPin.
 * - Re-tente si vérif 4xx (renvoi d’un nouveau code).
 * - Persisté via cy.session.
 * - Validation basée sur un signal RÉSEAU: /data/snapshots-private/*.jzon (auth only, query incluse).
 * - Désactive le Service Worker pendant les tests (sinon Cypress n’intercepte pas).
 */

/* ------------------------- Utils & commandes custom ------------------------- */

// Sélecteurs de liens Google Maps courants (web + deep-link mobile + shortlinks)
const GOOGLE_MAPS_ANCHOR_SELECTOR = [
    'a[href*="google.com/maps"]',
    'a[href*="maps.app.goo.gl"]',
    'a[href*="goo.gl/maps"]',
  ].join(', ');
  
  /**
   * Sélectionne un élément candidat parmi plusieurs en privilégiant un visible
   * et retente proprement en cas de fade-in (opacity: 0 sur un parent).
   *
   * @param {string} selector
   * @param {number} timeout
   * @param {boolean} requireVisible - si true, on échoue si rien n’est visible.
   * @returns {Chainable<JQuery<HTMLElement>>}
   */
  function pickVisibleFirst(selector, timeout, requireVisible) {
    // 1) On récupère tous les candidats (avec retry intégré de Cypress via timeout)
    return cy.get(selector, { includeShadowDom: true, timeout }).then(($all) => {
      if (!$all.length) {
        throw new Error(`[pickVisibleFirst] Aucun élément ne correspond au sélecteur: ${selector}`);
      }
  
      const $visible = $all.filter(':visible');
  
      // 2) Si la visibilité est obligatoire, on laisse Cypress RETENTER jusqu’à ce qu’un soit visible
      if (requireVisible) {
        return cy
          .get(selector, { includeShadowDom: true, timeout })
          .filter(':visible')
          .should('have.length.at.least', 1)
          .then(($v) => $v.first());
      }
  
      // 3) Sinon on prend le visible si possible, sinon le premier trouvé (et on log un warning)
      if ($visible.length) {
        return cy.wrap($visible.first());
      } else {
        cy.log('[Google Maps] ⚠️ Lien trouvé mais pas encore visible (probable fade-in). Validation de href quand même.');
        return cy.wrap($all.first());
      }
    });
  }
  
  /**
   * Vérifie qu’un lien Google Maps est présent et a un href valide.
   * - Attente résiliente : privilégie un lien visible, mais valide l’href même si caché (par défaut).
   * - Option `requireVisible: true` pour exiger la visibilité.
   *
   * @param {Object} opts
   * @param {number} [opts.timeout=20000]
   * @param {string} [opts.selector] - Pour cibler un lien spécifique si besoin.
   * @param {boolean} [opts.requireVisible=false] - Échoue si rien n’est visible.
   */
  Cypress.Commands.add('assertGoogleMapsLink', (opts = {}) => {
    const {
      timeout = 20000,
      selector,
      requireVisible = false,
    } = opts;
  
    const sel = selector || GOOGLE_MAPS_ANCHOR_SELECTOR;
  
    pickVisibleFirst(sel, timeout, requireVisible)
      .scrollIntoView({ ensureScrollable: false })
      .invoke('attr', 'href')
      .then((href) => {
        expect(href, 'href Google Maps').to.match(
          /https?:\/\/(?:www\.)?(?:google\.[^/]+\/maps|maps\.app\.goo\.gl|goo\.gl\/maps)/i
        );
        cy.log('Google Maps href = ' + href);
      });
  });
  
  /**
   * Compare la VRAIE URL du lien Google Maps avec une URL attendue (deep-link /dir).
   * - Décode les URLs avant comparaison.
   * - Tolère l’ordre des paramètres en vérifiant au minimum origin/destination/waypoints.
   * - Option `requireVisible` pour exiger la visibilité.
   * - ⚠️ Si l’app renvoie un shortlink (maps.app.goo.gl / goo.gl/maps), on échoue proprement :
   *   utiliser plutôt cy.assertGoogleMapsLink().
   *
   * @param {string} expectedUrl - ex: "https://www.google.com/maps/dir/?api=1&origin=...&destination=...&waypoints=...|..."
   * @param {Object} opts
   * @param {number} [opts.timeout=20000]
   * @param {string} [opts.selector] - Pour cibler un lien spécifique si besoin.
   * @param {boolean} [opts.requireVisible=false]
   */
  Cypress.Commands.add('assertGoogleMapsDeepLink', (expectedUrl, opts = {}) => {
    const {
      timeout = 20000,
      selector,
      requireVisible = false,
    } = opts;
  
    const candidateSelector = selector || 'a[href*="google.com/maps/dir/"]';
  
    if (!expectedUrl) {
      throw new Error('assertGoogleMapsDeepLink: expectedUrl est requis');
    }
  
    // Helpers de normalisation
    const decode = (u) => {
      try { return decodeURIComponent(u); } catch { return u; }
    };
    const getParams = (u) => {
      try {
        const url = new URL(u);
        return {
          origin: url.searchParams.get('origin') || '',
          destination: url.searchParams.get('destination') || '',
          waypoints: (url.searchParams.get('waypoints') || '').split('|').filter(Boolean),
          raw: u,
        };
      } catch {
        return { origin: '', destination: '', waypoints: [], raw: u };
      }
    };
  
    // On récupère le href réel via un lien visible si possible (ou le premier lien trouvé)
    pickVisibleFirst(candidateSelector, timeout, requireVisible)
      .invoke('attr', 'href')
      .then((actualHref) => {
        const decodedActual   = decode(actualHref || '');
        const decodedExpected = decode(expectedUrl);
  
        // Shortlinks → comparaison impossible ici
        if (/https?:\/\/(?:maps\.app\.goo\.gl|goo\.gl\/maps)\//i.test(decodedActual)) {
          throw new Error(
            '[assertGoogleMapsDeepLink] Le lien rendu est un shortlink mobile (maps.app.goo.gl / goo.gl/maps). ' +
            'Impossible de comparer aux paramètres attendus. Utilise plutôt cy.assertGoogleMapsLink() ' +
            'ou assure-toi que l’app rend un deep-link google.com/maps/dir/.'
          );
        }
  
        // On autorise uniquement le format google.com/maps/dir/ pour la comparaison "deep"
        if (!/https?:\/\/(?:www\.)?google\.[^/]+\/maps\/dir\//i.test(decodedActual)) {
          throw new Error(
            '[assertGoogleMapsDeepLink] Le lien ne correspond pas à un deep-link /maps/dir/. ' +
            'Utilise cy.assertGoogleMapsLink() pour une vérif générique, ou fournis un lien /dir en sortie.'
          );
        }
  
        const a = getParams(decodedActual);
        const e = getParams(decodedExpected);
  
        // Sanity checks minimales
        expect(a.origin, 'origin').to.contain(e.origin);
        expect(a.destination, 'destination').to.contain(e.destination);
  
        if (e.waypoints.length) {
          e.waypoints.forEach((wp) => {
            const found = a.waypoints.some((w) => decode(w) === decode(wp) || decode(w).includes(decode(wp)));
            expect(found, `waypoint "${wp}" présent`).to.eq(true);
          });
        }
  
        // Optionnel: égalité stricte
        // expect(decodedActual).to.eq(decodedExpected);
  
        cy.log('[assertGoogleMapsDeepLink] OK');
      });
  });
  
  /* ----------------------------- Commande loginOtp ---------------------------- */
  
  Cypress.Commands.add('loginOtp', () => {
    const email  = Cypress.env('E2E_LOGIN_EMAIL');
    const user   = Cypress.env('GMAIL_USER');
    const appPwd = Cypress.env('GMAIL_APP_PASSWORD'); // mot de passe d’app IMAP (16 chars)
  
    // ---- Timeouts (surchageables via env) ----
    const SENDPIN_TIMEOUT       = Number(Cypress.env('E2E_SENDPIN_TIMEOUT') || 120000); // 120 s
    const VERIFYPIN_TIMEOUT     = Number(Cypress.env('E2E_VERIFYPIN_TIMEOUT') || 60000); // 60 s
    const MAIL_SAFETY_DELAY_MS  = Number(Cypress.env('E2E_MAIL_DELAY_MS') || 1500); // 1.5 s
    const AUTH_READY_TIMEOUT    = Number(Cypress.env('E2E_AUTH_READY_TIMEOUT') || 30000); // 30 s
    const VALIDATE_AUTH_TIMEOUT = Number(Cypress.env('E2E_VALIDATE_AUTH_TIMEOUT') || 30000); // 30 s
    const AUTH_READY_SEL        = Cypress.env('E2E_AUTH_READY_SEL'); // optionnel: sélecteur d’un signal UI post-login
  
    // ---- Sélecteurs ----
    const emailCandidatesSel = 'input[type="email"], input[placeholder], input[data-testid="wf-input"]';
  
    const singleOtpSel = [
      'input[autocomplete="one-time-code"]',
      'input[inputmode="numeric"]',
      'input[type="tel"]',
      'input[name*="otp" i]',
      'input[name*="code" i]',
      'input[name*="pin" i]',
      'input[placeholder*="code" i]',
      'input[aria-label*="code" i]',
      'input[maxlength="5"]',
      'input[maxlength="6"]',
      'input[maxlength="7"]',
      'input[maxlength="8"]',
    ].join(', ');
  
    const cellsSel = [
      'input[maxlength="1"][type="text"]',
      'input[maxlength="1"][type="tel"]',
      'input[maxlength="1"][inputmode="numeric"]',
      'input[aria-label*="digit" i]',
      'input[aria-label*="chiffre" i]',
    ].join(', ');
  
    const editableSel = '[contenteditable=""],[contenteditable="true"],[role="textbox"]';
  
    // ---- Helpers DOM profonds ----
    function getAllDocs(win) {
      const docs = [win.document];
      Array.from(win.frames || []).forEach((fr) => { try { if (fr.document) docs.push(fr.document); } catch (_) {} });
      return docs;
    }
  
    function isVisible(win, el) {
      if (!el || !el.getBoundingClientRect) return false;
      const r = el.getBoundingClientRect();
      const s = win.getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s && s.visibility !== 'hidden' && s.display !== 'none';
    }
  
    function queryAllDeep(root, selector) {
      const out = [];
      const seen = new Set();
      function walk(node) {
        if (!node || seen.has(node)) return;
        seen.add(node);
        if (node.querySelectorAll) out.push(...node.querySelectorAll(selector));
        if (node.children) Array.from(node.children).forEach(walk);
        if (node.shadowRoot) walk(node.shadowRoot);
      }
      walk(root);
      return out;
    }
  
    function waitForOtpUi(retries = 30) {
      return cy.window({ log: false }).then((win) => {
        const docs = getAllDocs(win);
        for (const doc of docs) {
          const singles = queryAllDeep(doc, singleOtpSel).filter((el) => isVisible(win, el));
          if (singles.length) return { mode: 'single', el: singles[0] };
        }
        for (const doc of docs) {
          const cells = queryAllDeep(doc, cellsSel).filter((el) => isVisible(win, el));
          if (cells.length >= 5 && cells.length <= 8) return { mode: 'cells', els: cells };
        }
        for (const doc of docs) {
          const edits = queryAllDeep(doc, editableSel).filter((el) => isVisible(win, el));
          if (edits.length) return { mode: 'editable', el: edits[0] };
        }
        if (retries <= 0) throw new Error('OTP UI introuvable (unique, 5–8 cases ou contenteditable).');
        return cy.wait(1000).then(() => waitForOtpUi(retries - 1));
      });
    }
  
    const onlyDigits = (s) => String(s || '').replace(/\D+/g, '');
  
    // ---- SW killer ----
    const killSW = (win) => {
      try {
        if (win && win.navigator && win.navigator.serviceWorker) {
          win.navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((r) => r.unregister()));
        }
      } catch (_) {}
    };
  
    // ---------- Flow de login (persisté via cy.session) ----------
    cy.session(['otp-login', email], () => {
      // Intercepts réseau — posés tôt (avant visit)
      const snapRegex = /\/data\/snapshots-private\/.*\.jzon(?:\?.*)?$/;
      cy.intercept('POST', '**/sendPinForEmail*').as('sendPin');
      cy.intercept('POST', '**/getPasswordForEmailPin*').as('verifyPin');
      cy.intercept('POST', '**/v1/accounts:signInWithCustomToken*').as('fbSignIn');
      cy.intercept({ method: 'GET', url: snapRegex }).as('privateSnap'); // pour debug (on ne l’attend plus ici)
  
      // 1) Ouvre l’app, tue le SW et force l’OAuth dans le même onglet
      cy.visit('/', {
        onBeforeLoad(win) {
          killSW(win);
          cy.stub(win, 'open').callsFake((url) => { win.location.href = url; }).as('winOpen');
        },
      });
      cy.viewport(1280, 900);
  
      // Double sécurité: re-tuer le SW après boot
      cy.window({ timeout: 10000 }).then(killSW);
  
      // 2) Saisie e-mail
      cy.get(emailCandidatesSel, { includeShadowDom: true, timeout: 30000 }).then(($els) => {
        let el = $els.toArray().find((n) => {
          const ph  = (n.getAttribute('placeholder') || '').toLowerCase();
          const id  = (n.getAttribute('id') || '').toLowerCase();
          const nm  = (n.getAttribute('name') || '').toLowerCase();
          const dt  = (n.getAttribute('data-testid') || '').toLowerCase();
          return n.type === 'email' || /mail|e-?mail|courriel|adresse/.test(`${ph} ${id} ${nm} ${dt}`);
        });
        if (!el) {
          const $v = $els.filter(':visible');
          el = $v.get(0) || $els.get(0);
        }
        if (!el) throw new Error('Email input introuvable');
  
        cy.wrap(el)
          .scrollIntoView()
          .click({ force: true })
          .clear({ force: true })
          .type(email, { force: true });
      });
  
      // CTA "Envoyer code / Continuer"
      cy.contains(
        'button, [role="button"], a',
        /^(?:envoi.*code|send.*code|code.*pin|continuer|continue|next|suivant|log.*in|sign.*in)$/i,
        { includeShadowDom: true, timeout: 20000 }
      )
        .first()
        .should('not.be.disabled')
        .click({ force: true });
  
      // IMPORTANT : dater `since` APRÈS l’ACK de sendPin
      let since;
      cy.wait('@sendPin', { timeout: SENDPIN_TIMEOUT })
        .then(() => { since = Date.now(); })
        .then(() => cy.wait(MAIL_SAFETY_DELAY_MS))
  
        // 3) Récupère + saisit l’OTP, puis vérifie
        .then(() => {
          const attemptVerify = (maxTries = 2) => {
            return cy
              .task('getOtpGmail', {
                user,
                appPassword: appPwd,
                sinceTs: since,
                timeoutMs: 120_000,
              })
              .then((raw) => {
                const code = onlyDigits(raw);
                expect(code, 'OTP non vide').to.match(/^\d{5,8}$/);
                return waitForOtpUi().then((found) => ({ code, found }));
              })
              .then(({ code, found }) => {
                // Remplissage robuste
                if (found.mode === 'single') {
                  cy.wrap(found.el)
                    .scrollIntoView()
                    .click({ force: true })
                    .clear({ force: true })
                    .type(code, { force: true })
                    .type('{enter}', { force: true });
                } else if (found.mode === 'cells') {
                  const digits = code.split('');
                  found.els.forEach((el, idx) => {
                    if (idx < digits.length) cy.wrap(el).scrollIntoView().click({ force: true }).type(digits[idx], { force: true });
                  });
                  cy.wrap(found.els[Math.min(code.length - 1, found.els.length - 1)]).type('{enter}', { force: true });
                } else {
                  cy.wrap(found.el).scrollIntoView().click({ force: true }).type(code, { force: true });
                }
  
                // Attends la requête de vérif
                return cy.wait('@verifyPin', { timeout: VERIFYPIN_TIMEOUT }).then((inter) => {
                  const sc = inter?.response?.statusCode || 0;
                  cy.log(`[verifyPin] status = ${sc}`);
  
                  if (sc >= 200 && sc < 300) {
                    // Si présent, attendre le signIn Firebase (best effort)
                    cy.wait('@fbSignIn', { timeout: 60000 }).then(() => {}, () => {});
                    // Optionnel: signal UI si fourni (évite un wait réseau ici)
                    if (AUTH_READY_SEL) {
                      cy.get(AUTH_READY_SEL, { timeout: AUTH_READY_TIMEOUT }).should('be.visible');
                    }
                    return;
                  }
  
                  // 4xx => renvoi + nouvel essai
                  if (maxTries > 0) {
                    cy.log('[OTP] Vérif refusée — renvoi d’un nouveau code et nouvel essai');
  
                    const RESEND = /(renvoi|renvoyer|renvoie|resend|send.*new|nouveau.*code|new.*code)/i;
                    cy.get('body', { includeShadowDom: true }).then(($body) => {
                      const btn = Array.from($body[0].querySelectorAll('a,button,[role="button"]'))
                        .filter((el) => el.offsetParent !== null)
                        .find((el) => RESEND.test((el.textContent || '').trim()));
                      if (btn) {
                        cy.wrap(btn).click({ force: true });
                      } else {
                        cy.contains(
                          'button, [role="button"], a',
                          /^(?:envoi.*code|send.*code|code.*pin|continuer|continue|next|suivant)$/i,
                          { includeShadowDom: true, timeout: 15000 }
                        ).first().click({ force: true });
                      }
                    });
  
                    return cy
                      .wait('@sendPin', { timeout: SENDPIN_TIMEOUT })
                      .then(() => { since = Date.now(); })
                      .then(() => cy.wait(MAIL_SAFETY_DELAY_MS))
                      .then(() => attemptVerify(maxTries - 1));
                  }
  
                  throw new Error(`La vérification du PIN a échoué (status ${sc}).`);
                });
              });
          };
  
          return attemptVerify(2);
        })
        .then(() => {
          // Bypass Google si redirection
          cy.location('href', { timeout: 15000 }).then((href) => {
            if (href.includes('accounts.google.com') || Cypress.env('E2E_SKIP_GOOGLE')) {
              cy.log('[OAuth] Google détecté — bypass pour E2E');
              cy.visit('/'); // route post-login stable
            }
          });
        });
    }, {
      cacheAcrossSpecs: true,
  
      // --- VALIDATE: on valide l’auth via le signal réseau "snapshots-private" ---
      validate() {
        if (Cypress.env('E2E_DISABLE_SESSION_VALIDATE')) return;
  
        const snapRegex = /\/data\/snapshots-private\/.*\.jzon(?:\?.*)?$/;
  
        // Repose l’intercept AVANT visit()
        cy.intercept({ method: 'GET', url: snapRegex }).as('privateSnapValidate');
  
        const post = Cypress.env('E2E_POST_LOGIN_PATH') || '/';
        const sep = post.includes('?') ? '&' : '?';
  
        cy.visit(post + sep + 'e2e=' + Date.now(), {
          onBeforeLoad: (win) => {
            try {
              if (win && win.navigator && win.navigator.serviceWorker) {
                win.navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((r) => r.unregister()));
              }
            } catch (_) {}
          },
        });
  
        cy.document().its('readyState').should('eq', 'complete');
  
        // Laisse l’app déclencher la requête
        cy.wait(Number(Cypress.env('E2E_VALIDATE_WAIT') || 1500));
  
        // Si l’app ne déclenche pas la requête privée dans les temps, session KO
        cy.wait('@privateSnapValidate', { timeout: VALIDATE_AUTH_TIMEOUT });
      },
    });
  });
  