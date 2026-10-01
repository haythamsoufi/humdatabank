/**
 * Shared string sets for matrix/plugin config flags.
 *
 * Number handling stays at the call site: the form builder treats any non-zero
 * number as true, while entry-form ``__configFlag`` treats only ``1`` as true.
 */
export const TRUTHY_CONFIG_STRINGS = new Set(['true', '1', 'yes', 'on']);
export const FALSY_CONFIG_STRINGS = new Set(['false', '0', 'no', 'off', '']);

/** Entry-form flags also accept the single-letter yes/no forms. */
export const TRUTHY_FLAG_STRINGS = new Set(['true', '1', 'yes', 'y', 'on']);
export const FALSY_FLAG_STRINGS = new Set(['false', '0', 'no', 'n', 'off']);
