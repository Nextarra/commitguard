'use strict';
const $ = id => document.getElementById(id);
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
const usd = cents => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100);
let bootstrap, current, busy = false, editing = false, planKey = null, unverifiedPurchase = null;
const stateCopy = {
  DRAFT: ['QUOTE READY', 'Review your supplies.', 'Check the quantities, total and assumptions. Your approval commits to this exact quote.', 'idle'],
  APPROVED: ['COMMITMENT APPROVED', 'Exact quote. Your say.', 'Your approval is bound to this quote. Create one order next, then approve it as the payer.', 'idle'],
  CREATING: ['ORDER IN FLIGHT', 'Creating the order.', 'The intent is persisted. If interrupted, the app will not send another create request.', 'unknown'],
  CREATE_UNKNOWN: ['ORDER OUTCOME UNKNOWN', 'Stop. Check the merchant.', 'Creation may have succeeded, but no order ID was received. Keep the request ID below and investigate with the merchant. Do not create another purchase for this need.', 'unknown'],
  AWAITING_PAYER: ['PAYER APPROVAL NEEDED', 'A second, distinct approval.', 'The exact order exists. Payer approval at PayPal must happen before capture. Your quote approval alone cannot authorize payment.', 'idle'],
  READY_TO_CAPTURE: ['PAYER APPROVAL VERIFIED', 'Ready for one capture.', 'The original order matches your approved commitment. The app will check it again immediately before capture.', 'idle'],
  CAPTURING: ['CAPTURE IN FLIGHT', 'Checking the outcome.', 'The capture intent is persisted. Do not start another purchase.', 'unknown'],
  CAPTURE_UNKNOWN: ['CAPTURE OUTCOME UNKNOWN', 'Unknown does not mean failed.', 'The request may have reached the provider. Reconcile this original order to find out. Another capture is blocked.', 'unknown'],
  PAYMENT_PENDING: ['PAYMENT PENDING', 'Pending is not paid.', 'The provider reports a pending capture. Wait for settlement and reconcile. A second capture is blocked.', 'unknown'],
  COMPLETED: ['CAPTURE VERIFIED', 'The evidence checks out.', 'The original order and completed capture match your exact commitment. There is no second capture to send.', 'success'],
  REVIEW_REQUIRED: ['MANUAL REVIEW REQUIRED', 'Keep the facts. Stop payment.', 'The provider evidence or authentication needs review. Do not assume failure or try a new purchase. Reconcile or investigate with the merchant.', 'review'],
  CANCELLED: ['STOPPED LOCALLY', 'This app will not capture.', 'Local cancellation stops future payment attempts here. It is not a PayPal void, refund or fulfillment cancellation.', 'idle'],
};
const scenarioHelp = {
  happy: 'Follow the complete simulated create, payer approval and capture flow.',
  lost_response: 'The fixture records a successful capture, then drops its response. Watch how recovery avoids a second capture.',
  timeout_before: 'The capture never completes in this fixture. Recovery keeps the outcome unknown and blocks another attempt.',
  pending: 'A capture stays pending. Settle the fixture, then verify the original order.',
  auth_error: 'The simulated provider rejects authentication. No capture succeeds; the app stops for review.',
  mismatch: 'The fixture returns a capture in EUR against a USD commitment. The payment engine rejects the evidence.',
  create_timeout: 'The fixture creates an order but loses the response. Without an order ID, the app stops for manual investigation.',
};
function message(text, error = false) { $('message').hidden = !text; $('message').textContent = text || ''; $('message').className = error ? 'message error' : 'message'; }
async function api(path, body) {
  const response = await fetch(path, { method: body ? 'POST' : 'GET', headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': bootstrap.csrf } : {}, body: body ? JSON.stringify(body) : undefined });
  let data; try { data = await response.json(); } catch { throw new Error('The local server response was interrupted. Reload and check purchase history before trying again.'); }
  if (!response.ok) throw new Error(data.message || 'Request could not be completed.');
  return data;
}
function action(text, fn, cls = 'primary') { const b = el('button', text, cls + ' full'); b.type = 'button'; b.disabled = busy; b.addEventListener('click', fn); return b; }
async function run(fn) {
  if (busy) return;
  busy = true; message(''); document.body.setAttribute('aria-busy', 'true');
  document.querySelectorAll('button').forEach(b => b.disabled = true);
  try { await fn(); }
  catch (err) { message(err.message || 'An unexpected error stopped this action.', true); }
  finally { busy = false; document.body.removeAttribute('aria-busy'); document.querySelectorAll('button').forEach(b => b.disabled = false); if (current) render(); }
}
function needsRecovery(p) { return p && (unverifiedPurchase === p.id || ['CREATE_UNKNOWN', 'CAPTURE_UNKNOWN', 'PAYMENT_PENDING', 'REVIEW_REQUIRED'].includes(p.state) || (p.state === 'COMPLETED' && !(p.capture_id && p.last_capture_evidence))); }
function upsert(p) {
  const previous = current;
  if (unverifiedPurchase === p.id) unverifiedPurchase = null;
  current = p; editing = false;
  const index = bootstrap.purchases.findIndex(x => x.id === p.id);
  if (index === -1) bootstrap.purchases.unshift(p); else bootstrap.purchases[index] = p;
  localStorage.setItem('commitguard.current', p.id); render(); history();
  if (window.matchMedia('(max-width: 760px)').matches && previous?.state !== p.state) {
    if (needsRecovery(p)) { $('mobile-recovery-title').focus(); $('mobile-recovery').scrollIntoView({ block: 'start' }); }
    else if (needsRecovery(previous)) $('state-title').focus();
  }
}
async function refreshSavedPurchase() {
  await run(async () => {
    try { upsert(await api('/api/purchases/' + current.id)); message('Saved purchase reloaded. Check its status before taking another action.'); }
    catch { throw new Error('The local server is still unavailable. Restart it with the same data directory, then refresh this saved purchase.'); }
  });
}
async function command(path, extra = {}) {
  await run(async () => {
    const id = current.id;
    try { upsert(await api('/api/' + path, { id, ...extra })); }
    catch (error) {
      // A failed response does not prove the mutation failed. Read persisted
      // state; never replay the POST or continue from an unverified snapshot.
      try { upsert(await api('/api/purchases/' + id)); }
      catch {
        unverifiedPurchase = id; editing = false;
        throw new Error('Connection lost. The action outcome is not confirmed. Restart the local server with the same data directory, then refresh the saved purchase. Do not start over.');
      }
      if (error instanceof TypeError || error.message.startsWith('The local server response was interrupted.')) {
        message('The action response was lost. Saved purchase state was recovered without repeating the action. Check the verified status below.');
        return;
      }
      throw error;
    }
  });
}
function history() {
  $('history-count').textContent = bootstrap.purchases.length;
  $('history-list').replaceChildren();
  if (!bootstrap.purchases.length) $('history-list').append(el('p', 'No purchase plans in this browser session yet.', 'muted'));
  for (const p of bootstrap.purchases) {
    const b = el('button', `${usd(p.plan.total_cents)} · ${p.state.replaceAll('_', ' ')} · ${p.id.slice(0, 8)}`);
    b.type = 'button'; b.addEventListener('click', () => run(async () => { upsert(await api('/api/purchases/' + p.id)); $('history').hidden = true; $('history-toggle').setAttribute('aria-expanded', 'false'); }));
    $('history-list').append(b);
  }
}
function render() {
  if (!current) return;
  const p = current, plan = p.plan;
  $('empty-plan').hidden = true; $('plan-content').hidden = false;
  $('quote-status').textContent = p.state.replaceAll('_', ' ');
  $('merchant').textContent = plan.merchant.name + ' · Catalog ' + plan.merchant.catalog_version;
  $('proposal-label').textContent = p.planner_mode === 'fixture' ? 'DETERMINISTIC FIXTURE PROPOSAL' : 'STRUCTURED AI PROPOSAL · POLICY CHECKED';
  $('explanation').textContent = plan.explanation;
  $('questions').replaceChildren(); $('questions').hidden = !plan.questions.length;
  if (plan.questions.length) { $('questions').append(el('strong', 'CLARIFICATION NEEDED')); plan.questions.forEach(q => $('questions').append(el('p', q))); $('questions').append(el('p', 'Update your brief and build a new plan. No payment is available for this proposal.')); }
  $('lines').replaceChildren();
  for (const line of plan.items) {
    const tr = el('tr'), name = el('td', line.name); name.append(el('small', line.sku + ' · ' + usd(line.unit_cents) + ' each'));
    const qtyCell = el('td'), qty = el('input'); qty.type = 'number'; qty.min = '1'; qty.max = String(Math.min(10, bootstrap.catalog.find(x => x.sku === line.sku).stock)); qty.step = '1'; qty.value = line.quantity; qty.className = 'qty'; qty.dataset.sku = line.sku; qty.setAttribute('aria-label', 'Quantity for ' + line.name); qty.disabled = !editing; qtyCell.append(qty);
    tr.append(name, qtyCell, el('td', usd(line.line_cents), 'numeric')); $('lines').append(tr);
  }
  $('total').textContent = usd(plan.total_cents); $('remaining').textContent = usd(plan.budget_cents - plan.total_cents) + ' within your budget';
  $('fingerprint').textContent = 'SHA-256 · ' + p.plan_hash.slice(0, 24) + '…'; $('fingerprint').title = p.plan_hash;
  $('quote-actions').replaceChildren(); $('edit-controls').hidden = !editing;
  $('approval-summary').hidden = !p.approval_hash; $('approval-summary').replaceChildren();
  if (p.approval_hash) { $('approval-summary').append(el('strong', p.local_cancelled_at ? 'Local payment permission revoked' : '✓ Exact quote approved')); $('approval-summary').append(el('div', `${usd(plan.total_cents)} USD · ${plan.items.length} supply lines · approval valid for 24 hours`)); }
  if (!editing && p.state === 'DRAFT' && plan.items.length && !plan.questions.length) $('quote-actions').append(action(`Approve exact ${usd(plan.total_cents)} quote`, () => command('approve', { plan_hash: p.plan_hash })));
  if (!editing && ['DRAFT', 'APPROVED'].includes(p.state) && plan.items.length) $('quote-actions').append(action('Adjust quantities', () => { editing = true; render(); document.querySelector('.qty')?.focus(); }, 'secondary'));
  if (!editing && p.state === 'APPROVED') $('quote-actions').append(action('Create one checkout order →', () => command('create')));
  if (!editing && ['DRAFT', 'APPROVED', 'AWAITING_PAYER', 'READY_TO_CAPTURE'].includes(p.state)) $('quote-actions').append(action('Stop this purchase locally', () => command('cancel'), 'quiet'));
  const incompleteProof = p.state === 'COMPLETED' && !(p.capture_id && p.last_capture_evidence);
  const copy = (p.state === 'DRAFT' && plan.questions.length ? ['CLARIFICATION NEEDED', 'A clearer brief comes first.', 'Answer the planner’s questions in your brief, then build a new plan. Payment is unavailable until the supplies are clear.', 'idle'] : incompleteProof ? ['RECEIPT EVIDENCE INCOMPLETE', 'Recover the original receipt.', 'This older record is missing capture proof. Read the original order; no new capture is available.', 'unknown'] : stateCopy[p.state]) || ['UNKNOWN STATE', 'Review this purchase.', 'No payment action is available.', 'review'];
  $('state-label').textContent = copy[0]; $('state-title').textContent = copy[1]; $('state-description').textContent = copy[2] + (p.local_cancelled_at && p.state !== 'CANCELLED' ? ' Local payment permission remains revoked. Provider evidence cannot restore it.' : ''); $('payment-state').className = 'payment-state ' + copy[3];
  $('mobile-recovery').hidden = !needsRecovery(p);
  $('mobile-recovery').className = 'mobile-recovery panel ' + copy[3];
  $('mobile-recovery-status').textContent = copy[0];
  $('mobile-recovery-title').textContent = copy[1];
  $('mobile-recovery-amount').textContent = `Committed ${usd(plan.total_cents)} USD · ${p.payment_mode === 'fixture' ? 'Simulated' : 'Sandbox'}`;
  $('mobile-recovery-description').textContent = p.paypal_id ? 'Check the original order. This does not send another payment.' : 'No order ID was received. Keep the saved request ID and investigate before making another purchase.';
  $('mobile-recovery-actions').replaceChildren();
  if (needsRecovery(p)) {
    if (p.paypal_id) $('mobile-recovery-actions').append(action('Check original order status', () => command('reconcile')));
    else $('mobile-recovery-actions').append(action('Review saved request ID', () => $('state-title').focus(), 'secondary'));
  }
  $('payment-actions').replaceChildren();
  if (p.state === 'AWAITING_PAYER' && p.payment_mode === 'fixture') $('payment-actions').append(action('Simulate PayPal payer approval', () => command('payer-fixture'), 'secondary'));
  if (p.state === 'AWAITING_PAYER' && p.payment_mode === 'sandbox' && p.approval_url) {
    const a = el('a', 'Approve at PayPal sandbox ↗', 'primary full'); a.href = p.approval_url; a.target = '_blank'; a.rel = 'noopener noreferrer'; $('payment-actions').append(a);
  }
  if (p.state === 'READY_TO_CAPTURE' && !p.local_cancelled_at && !p.capture_observed) $('payment-actions').append(action(`Capture ${usd(plan.total_cents)} once`, () => command('capture')));
  if (p.paypal_id && (incompleteProof || !['COMPLETED', 'CREATING', 'CAPTURING'].includes(p.state))) $('payment-actions').append(action('Reconcile original order ↻', () => command('reconcile'), p.state === 'CAPTURE_UNKNOWN' ? 'primary' : 'secondary'));
  if (p.state === 'PAYMENT_PENDING' && p.payment_mode === 'fixture') $('payment-actions').append(action('Settle pending fixture', () => command('settle-fixture'), 'quiet'));
  if (p.state === 'CREATE_UNKNOWN') { const n = el('div', undefined, 'approval-summary'); n.append(el('strong', 'Saved create request ID')); n.append(el('code', p.create_key)); $('payment-actions').append(n); }
  $('metrics').hidden = !p.rehearsal_metrics;
  if (p.rehearsal_metrics) { $('capture-calls').textContent = p.rehearsal_metrics.capture_calls; $('charge-count').textContent = p.rehearsal_metrics.charge_count; }
  $('receipt').hidden = p.state !== 'COMPLETED' || incompleteProof;
  if (p.state === 'COMPLETED') { $('receipt-amount').textContent = usd(plan.total_cents) + ' USD' + (p.payment_mode === 'fixture' ? ' · SIMULATED' : ' · SANDBOX'); $('receipt-order').textContent = p.paypal_id; $('receipt-capture').textContent = p.capture_id; }
  if (unverifiedPurchase === p.id) {
    $('quote-status').textContent = 'SAVED STATUS UNVERIFIED';
    $('quote-actions').replaceChildren(); $('edit-controls').hidden = true;
    $('state-label').textContent = 'LOCAL CONNECTION LOST';
    $('state-title').textContent = 'Reload the facts before acting.';
    $('state-description').textContent = 'The last action may have reached the server. Payment actions are paused until this saved purchase can be read. Keep the same browser session and data directory.';
    $('payment-state').className = 'payment-state unknown';
    $('payment-actions').replaceChildren(action('Refresh saved purchase', refreshSavedPurchase));
    $('metrics').hidden = true;
    $('receipt').hidden = true;
    $('mobile-recovery-status').textContent = 'LOCAL CONNECTION LOST';
    $('mobile-recovery-title').textContent = 'Reload the facts before acting.';
    $('mobile-recovery-description').textContent = 'Restart the local server with its original data directory, then refresh. This reads saved state without sending another payment.';
    $('mobile-recovery-actions').replaceChildren(action('Refresh saved purchase', refreshSavedPurchase));
  }
  $('trace-list').replaceChildren(); $('trace-count').textContent = p.trace.length + ' events';
  for (const event of p.trace) { const li = el('li'), strong = el('strong', event.kind.replaceAll('_', ' ')), time = el('time', new Date(event.at * 1000).toLocaleTimeString([], { hour12: false })); time.dateTime = new Date(event.at * 1000).toISOString(); strong.append(time); li.append(strong, el('p', event.message)); $('trace-list').append(li); }
}
$('brief-form').addEventListener('submit', event => {
  event.preventDefault();
  run(async () => {
    const budget = Number($('budget').value).toFixed(2);
    const snapshot = JSON.stringify({ need: $('need').value, budget, currency: 'USD', scenario: $('scenario').value });
    if (!planKey || planKey.snapshot !== snapshot) planKey = { snapshot, key: crypto.randomUUID() };
    const p = await api('/api/plan', { ...JSON.parse(snapshot), request_key: planKey.key }); upsert(p);
    if (p.plan.questions.length) message('The planner needs clarification. Update the brief and build a new plan.');
    else message('Plan ready. Review every line and approve the exact amount.');
    $('quote-heading').setAttribute('tabindex', '-1'); $('quote-heading').focus({ preventScroll: true });
  });
});
$('save-edit').addEventListener('click', () => {
  const inputs = [...document.querySelectorAll('.qty')];
  if (inputs.some(q => !q.checkValidity())) { inputs.find(q => !q.checkValidity()).reportValidity(); return; }
  const items = inputs.map(q => ({ sku: q.dataset.sku, quantity: Number(q.value) })); command('revise', { items });
});
$('export-receipt').addEventListener('click', () => {
  const evidence = { application: 'CommitGuard', payment_mode: current.payment_mode, planner_mode: current.planner_mode, notice: current.payment_mode === 'fixture' ? 'Simulated provider evidence. No external payment occurred.' : 'PayPal sandbox only; no real money.', purchase: current };
  const url = URL.createObjectURL(new Blob([JSON.stringify(evidence, null, 2)], { type: 'application/json' })); const a = el('a'); a.href = url; a.download = `commitguard-${current.id}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
const presets = { repair: 'I need patches, tyre levers and gloves for 20 bike repairs.', tune: 'I need chain lubricant, cloths and gloves for a bicycle tune-up bench.', clarify: 'Help me prepare for next week at the workshop.' };
document.querySelectorAll('[data-preset]').forEach(b => b.addEventListener('click', () => { $('need').value = presets[b.dataset.preset]; $('need').focus(); }));
$('scenario').addEventListener('change', () => $('scenario-help').textContent = scenarioHelp[$('scenario').value]);
$('history-toggle').addEventListener('click', () => { $('history').hidden = !$('history').hidden; $('history-toggle').setAttribute('aria-expanded', String(!$('history').hidden)); });
(async () => {
  try {
    bootstrap = await api('/api/bootstrap');
    $('mode-name').textContent = bootstrap.payment_mode === 'fixture' ? 'Local rehearsal' : 'PayPal sandbox';
    $('environment').replaceChildren(el('strong', bootstrap.payment_mode === 'fixture' ? 'FIXTURE REHEARSAL' : 'PAYPAL SANDBOX'));
    $('environment').append(el('span', `${bootstrap.planner_mode === 'fixture' ? 'Deterministic fixture planner' : 'External structured AI adapter'} · ${bootstrap.payment_mode === 'fixture' ? 'simulated PayPal' : 'sandbox payments only'} · no real money.`));
    $('planner-note').textContent = bootstrap.planner_mode === 'fixture' ? 'This is a deterministic rehearsal planner, not a connected AI model.' : 'A structured AI model proposes. Server policy validates. You authorize the exact quote.';
    $('scenario-wrap').hidden = bootstrap.payment_mode !== 'fixture';
    for (const product of bootstrap.catalog) { const row = el('div', undefined, 'catalog-item'), top = el('div'); top.append(el('strong', product.name), el('span', usd(product.price_cents))); row.append(top, el('p', product.description + ' · Stock: ' + product.stock)); $('catalog-list').append(row); }
    history();
    const query = new URLSearchParams(location.search), id = query.get('purchase') || query.get('cancelled') || localStorage.getItem('commitguard.current');
    const saved = bootstrap.purchases.find(p => p.id === id); if (saved) upsert(saved);
    if (query.has('purchase')) message('Returned from the provider. This redirect is not proof of approval or payment. Reconcile the original order.');
    if (query.has('cancelled')) message('Returned from provider cancellation. Use “Stop this purchase locally” to prevent capture here. No refund or void was performed.');
  } catch (err) { message('Cannot load the local app: ' + err.message, true); $('plan-button').disabled = true; }
})();
