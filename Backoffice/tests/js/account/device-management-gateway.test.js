/**
 * Account device management — safe JSON via apiFetch on gateway HTML responses.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('device-management.js', () => {
  beforeEach(async () => {
    vi.resetModules();
    document.body.innerHTML = `
      <input name="csrf_token" value="tok">
      <table><tbody><tr>
        <td></td><td></td>
        <td><button type="button" class="remove-device-btn" data-device-id="42">Remove</button></td>
      </tr></tbody></table>
    `;
    window.showAlert = vi.fn();
    window.showDangerConfirmation = (_msg, cb) => cb();
    window.apiFetch = vi.fn().mockRejectedValue(new Error('HTTP 502: Bad Gateway'));
    await import('../../../app/static/js/account/device-management.js');
    window.initAccountDeviceManagement();
  });

  afterEach(() => {
    delete window.initAccountDeviceManagement;
    delete window.apiFetch;
    delete window.showAlert;
    delete window.showDangerConfirmation;
    document.body.innerHTML = '';
  });

  it('shows bounded error on gateway HTML/502 instead of SyntaxError', async () => {
    document.querySelector('.remove-device-btn').click();
    await vi.waitFor(() => expect(window.showAlert).toHaveBeenCalled());
    expect(window.apiFetch).toHaveBeenCalled();
    expect(window.showAlert).toHaveBeenCalledWith(
      expect.stringMatching(/502|Bad Gateway|HTTP/),
      'error',
    );
    expect(window.showAlert.mock.calls[0][0]).not.toMatch(/Unexpected token/);
  });
});
