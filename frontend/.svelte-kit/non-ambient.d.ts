
// this file is generated — do not edit it


declare module "svelte/elements" {
	export interface HTMLAttributes<T> {
		'data-sveltekit-keepfocus'?: true | '' | 'off' | undefined | null;
		'data-sveltekit-noscroll'?: true | '' | 'off' | undefined | null;
		'data-sveltekit-preload-code'?:
			| true
			| ''
			| 'eager'
			| 'viewport'
			| 'hover'
			| 'tap'
			| 'off'
			| undefined
			| null;
		'data-sveltekit-preload-data'?: true | '' | 'hover' | 'tap' | 'off' | undefined | null;
		'data-sveltekit-reload'?: true | '' | 'off' | undefined | null;
		'data-sveltekit-replacestate'?: true | '' | 'off' | undefined | null;
	}
}

export {};


declare module "$app/types" {
	export interface AppTypes {
		RouteId(): "/" | "/auth" | "/auth/email" | "/auth/email/verify" | "/developer" | "/leagues" | "/leagues/[uid]" | "/login" | "/oauth" | "/oauth/consent" | "/profile" | "/rankings" | "/tournaments" | "/tournaments/new" | "/tournaments/[uid]" | "/users" | "/users/[uid]";
		RouteParams(): {
			"/leagues/[uid]": { uid: string };
			"/tournaments/[uid]": { uid: string };
			"/users/[uid]": { uid: string }
		};
		LayoutParams(): {
			"/": { uid?: string };
			"/auth": Record<string, never>;
			"/auth/email": Record<string, never>;
			"/auth/email/verify": Record<string, never>;
			"/developer": Record<string, never>;
			"/leagues": { uid?: string };
			"/leagues/[uid]": { uid: string };
			"/login": Record<string, never>;
			"/oauth": Record<string, never>;
			"/oauth/consent": Record<string, never>;
			"/profile": Record<string, never>;
			"/rankings": Record<string, never>;
			"/tournaments": { uid?: string };
			"/tournaments/new": Record<string, never>;
			"/tournaments/[uid]": { uid: string };
			"/users": { uid?: string };
			"/users/[uid]": { uid: string }
		};
		Pathname(): "/" | "/auth" | "/auth/" | "/auth/email" | "/auth/email/" | "/auth/email/verify" | "/auth/email/verify/" | "/developer" | "/developer/" | "/leagues" | "/leagues/" | `/leagues/${string}` & {} | `/leagues/${string}/` & {} | "/login" | "/login/" | "/oauth" | "/oauth/" | "/oauth/consent" | "/oauth/consent/" | "/profile" | "/profile/" | "/rankings" | "/rankings/" | "/tournaments" | "/tournaments/" | "/tournaments/new" | "/tournaments/new/" | `/tournaments/${string}` & {} | `/tournaments/${string}/` & {} | "/users" | "/users/" | `/users/${string}` & {} | `/users/${string}/` & {};
		ResolvedPathname(): `${"" | `/${string}`}${ReturnType<AppTypes['Pathname']>}`;
		Asset(): "/apple-touch-icon.png" | "/favicon.svg" | "/icon-192.png" | "/icon-512.png" | "/manifest.webmanifest" | string & {};
	}
}