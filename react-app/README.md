# CRM Data Health Scanner — React client

Standalone React frontend, built with [Vite](https://vite.dev/).

## Available Scripts

### `npm run dev` (alias: `npm start`)

Runs the app in development mode on [http://localhost:3000/app/](http://localhost:3000/app/).
The `/app/` prefix matches the path Catalyst hosts the client under, so relative
asset URLs behave the same in development and production.

### `npm run build`

Builds the app for production into the `build` folder. The output is the
Catalyst deploy artifact: hashed JS/CSS bundles, the contents of `public/`, and
a copy of `client-package.json`.

### `npm run preview`

Serves the contents of `build` locally for a quick check of a production build.

## Catalyst

`catalyst.json` points the client resource at `react-app/build` and runs
`npm run build` as its pre-deploy and pre-serve script, so `catalyst deploy` and
`catalyst serve` build the frontend before packaging it.

`client-package.json` stays at the package root. It is Catalyst deploy
configuration — it sets the hosted homepage to `/__catalyst/auth/login` and the
post-login redirect to `index.html` — and is copied into `build` by the build.
