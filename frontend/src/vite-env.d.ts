/// <reference types="vite/client" />

/** Build stamp injected by vite.config.ts (`define`). Present in every build,
 *  including dev, so nothing has to guard against it being undefined. */
declare const __BUILD_ID__: string;
