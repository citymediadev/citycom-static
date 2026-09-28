/**
 * Complianz — Interactivity API navigation bridge (WordPress 7.0+).
 *
 * Uses ONLY the public Interactivity API: the core/router store's `state.url`
 * plus `watch()`. When the router performs a client-side navigation it updates
 * `state.url`, which re-runs the watcher. We translate that into a DOM
 * CustomEvent (`cmplz_router_navigated`) that the classic banner script listens
 * for. The classic bundle never touches iAPI internals, and this module never
 * touches the banner — the boundary is a one-way event.
 *
 * No private/internal API, no globals, no History monkey-patching. The
 * deprecated `state.navigation.*` is intentionally not used.
 */
import { store, watch } from '@wordpress/interactivity';

const { state } = store( 'core/router' );

let isFirstRun = true;

watch( () => {
	// Establish the reactive dependency on the router URL.
	const url = state.url;

	// The watcher runs once synchronously on registration; that initial run is
	// not a navigation, so skip it.
	if ( isFirstRun ) {
		isFirstRun = false;
		return;
	}

	// Defer so the router finishes its region re-render and its own stylesheet
	// enable/disable pass before we react. The classic-side handlers are
	// idempotent, so the extra safety-net tick is harmless.
	requestAnimationFrame( () => {
		document.dispatchEvent(
			new CustomEvent( 'cmplz_router_navigated', { detail: { url } } )
		);
		setTimeout( () => {
			document.dispatchEvent(
				new CustomEvent( 'cmplz_router_navigated', { detail: { url } } )
			);
		}, 100 );
	} );
} );
