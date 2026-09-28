function cmplz_acs_send_consent( marketing ) {
	window.amznConsent()
		.setCountryCode( '{country_code}' )
		.setEnableAdStorage( marketing )
		.setEnableUserData( marketing )
		.build();
}

function cmplz_acs_get_cookie( name ) {
	var match = document.cookie.match( '(?:^|;)\\s*' + name + '\\s*=\\s*([^;]+)' );
	return match ? match[1] : '';
}

function cmplz_acs_on_library_loaded() {
	var marketing = cmplz_acs_get_cookie( 'cmplz_marketing' ) === 'allow' ? true : false;
	cmplz_acs_send_consent( marketing );
}

function cmplz_acs_on_categories_consent( e ) {
	if ( typeof window.amznConsent !== 'function' ) { return; }
	var marketing = cmplz_in_array( 'marketing', e.detail.categories ) ? true : false;
	cmplz_acs_send_consent( marketing );
}

function cmplz_acs_on_revoke() {
	if ( typeof window.amznConsent !== 'function' ) { return; }
	cmplz_acs_send_consent( false );
}

var cmplz_acs_script = document.createElement( 'script' );
cmplz_acs_script.src = 'https://c.amazon-adsystem.com/aat/amzn-consent.js';
cmplz_acs_script.onload = cmplz_acs_on_library_loaded;
document.head.appendChild( cmplz_acs_script );

document.addEventListener( 'cmplz_fire_categories', cmplz_acs_on_categories_consent );
document.addEventListener( 'cmplz_revoke', cmplz_acs_on_revoke );
