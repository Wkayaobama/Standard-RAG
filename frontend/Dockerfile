FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

# `node_modules` is a named volume (see docker-compose.yml) so the source bind
# mount can't clobber it. The side effect: a rebuilt image's fresh `npm install`
# never reaches the running container — the existing volume is reused as-is. So
# a dependency the agent adds during an iterate (e.g. `jspdf`) would never land
# in the preview, and Vite fails with "Failed to resolve import". Re-running
# install on every start syncs the volume with the current package.json: it's
# near-instant when nothing changed, and installs the new dep when it did. Vite
# always starts afterwards (`;`) so a transient registry hiccup can't take the
# preview fully down — it falls back to whatever's already in the volume.
CMD ["sh", "-c", "npm install --no-audit --no-fund; npm run dev"]
