/**
 * Entry form — validation questions panel (answer + field highlight).
 */
(function () {
    const banner = document.getElementById('validation-questions-banner');
    if (!banner) return;

    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const list = document.getElementById('validation-questions-list');
    const toggle = document.getElementById('validation-questions-toggle');

    if (toggle && list) {
        toggle.addEventListener('click', () => list.classList.toggle('hidden'));
    }

    banner.querySelectorAll('.validation-answer-submit').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const card = btn.closest('.validation-question-card');
            const qid = btn.dataset.questionId;
            const input = card?.querySelector('.validation-answer-input');
            const answer = (input?.value || '').trim();
            if (!answer) return;
            const resp = await fetch(`/api/v1/validation-questions/${qid}/answer`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrf,
                    Accept: 'application/json',
                },
                body: JSON.stringify({ answer_text: answer }),
            });
            if (resp.ok && card) {
                card.remove();
            }
        });
    });

    document.querySelectorAll('.validation-question-card[data-form-item-id]').forEach((card) => {
        const itemId = card.dataset.formItemId;
        const field = document.querySelector(`[data-item-id="${itemId}"], #form-item-${itemId}`);
        if (field) {
            field.classList.add('ring-2', 'ring-amber-400', 'rounded');
        }
    });

    const params = new URLSearchParams(window.location.search);
    const highlight = params.get('highlight_validation');
    if (highlight) {
        const card = banner.querySelector(`[data-question-id="${highlight}"]`);
        card?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
})();
