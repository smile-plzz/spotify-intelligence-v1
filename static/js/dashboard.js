/**
 * Spotify Intelligence — Dashboard client (Figma-match)
 * Handles: refresh, live polling, library tabs, time formatting,
 * data formatting from API responses into the design-system markup.
 */

(function () {
  'use strict';

  const App = {
    charts: {},
    liveInterval: null,
    refreshInterval: null,

    init() {
      this.attachNav();
      this.attachRefreshButtons();
      if (this.attachLibraryTabs) this.attachLibraryTabs();
      if (this.attachAuthCallbackSteps) this.attachAuthCallbackSteps();
      this.refreshAll();
      this.startLivePolling();
    },

    /* ===== Navigation ===== */
    attachNav() {
      document.querySelectorAll('.nav-link:not([data-bound])').forEach((link) => {
        link.setAttribute('data-bound', 'true');
        link.addEventListener('click', (e) => {
          e.preventDefault();
          const href = link.getAttribute('href');
          if (!href || href.startsWith('#')) return;
          this.navigateTo(href);
        });
      });

      document.querySelectorAll('.mobile-tab:not([data-bound])').forEach((tab) => {
        tab.setAttribute('data-bound', 'true');
        tab.addEventListener('click', (e) => {
          e.preventDefault();
          const href = tab.getAttribute('href');
          if (!href) return;
          this.navigateTo(href);
        });
      });

      const backLink = document.querySelector('a[href*="Overview.dc.html"]');
      if (backLink) {
        backLink.addEventListener('click', (e) => {
          e.preventDefault();
          this.navigateTo('Overview.dc.html');
        });
      }
    },

    navigateTo(page) {
      window.location.href = page;
    },

    /* ===== Refresh ===== */
    attachRefreshButtons() {
      document.querySelectorAll('.refresh-btn, .btn-action, [data-action="refresh"]').forEach((btn) => {
        if (btn.hasAttribute('data-refresh-bound')) return;
        btn.setAttribute('data-refresh-bound', 'true');
        btn.addEventListener('click', () => this.refreshAll());
      });
    },

    async refreshAll() {
      try {
        await Promise.all([
          this.loadOverview(),
          this.loadTaste(),
          this.loadEvolution(),
          this.loadListening(),
          this.loadLibrary(),
          this.loadIntelligence(),
          this.loadSettings(),
          this.loadRecentActivity(),
        ]);
      } catch (e) {
        console.warn('Refresh error:', e);
      }
    },

    /* ===== Overview ===== */
    async loadOverview() {
      try {
        const [summary, genres, topArtists, topTracks, analytics] = await Promise.all([
          this.fetchJSON('/api/summary'),
          this.fetchJSON('/api/genres'),
          this.fetchJSON('/api/top-artists'),
          this.fetchJSON('/api/top-tracks'),
          this.fetchJSON('/api/analytics'),
        ]);

        this.renderNowPlaying(summary);
        this.renderStatGrid(summary);
        this.renderTopArtists(topArtists);
        this.renderTopTracks(topTracks);
        this.renderGenreCloud(genres);
        this.renderGenreFamilies(genres);
        this.renderArchetype(analytics);
        this.renderMusicDNA(analytics);
      } catch (e) {
        console.warn('Overview load error:', e);
      }
    },

    renderNowPlaying(summary) {
      const cp = summary.currently_playing;
      const badge = document.querySelector('.now-playing-badge');
      const trackName = document.querySelector('.now-playing-track-name');
      const trackArtist = document.querySelector('.now-playing-artist');
      const progressEl = document.querySelector('.now-playing-progress');
      const progressFill = document.querySelector('.now-playing-progress-fill');
      const openLink = document.querySelector('.btn-open');

      if (!cp) {
        if (badge) badge.textContent = 'Nothing playing';
        if (trackName) trackName.textContent = 'Not playing';
        if (trackArtist) trackArtist.textContent = '';
        if (progressEl) progressEl.style.display = 'none';
        if (openLink) openLink.style.display = 'none';
        return;
      }

      if (badge) badge.textContent = 'Now playing';
      if (trackName) trackName.textContent = cp.name;
      if (trackArtist) trackArtist.textContent = cp.artist + ' — ' + cp.album;
      if (progressEl) {
        progressEl.style.display = 'block';
        if (cp.duration_ms && cp.duration_ms > 0) {
          const pct = Math.min(100, (cp.progress_ms / cp.duration_ms) * 100);
          if (progressFill) progressFill.style.width = pct + '%';
        }
      }
      if (openLink) openLink.style.display = 'inline-block';
    },

    renderStatGrid(summary) {
      const grid = document.querySelector('.stat-grid');
      if (!grid) return;

      const stats = [
        { label: 'Total plays', value: summary.total_plays },
        { label: 'Unique artists', value: summary.unique_artists },
        { label: 'Unique tracks', value: summary.unique_tracks },
        { label: 'Unique albums', value: summary.unique_albums },
        { label: 'Saved tracks', value: summary.saved_tracks },
        { label: 'Saved albums', value: summary.saved_albums },
        { label: 'Playlists', value: summary.playlists },
      ];

      // Find how many stat cards are in the template
      const existingCards = grid.querySelectorAll('.stat-card');
      const count = Math.min(stats.length, existingCards.length);

      for (let i = 0; i < count; i++) {
        const card = existingCards[i];
        const valEl = card.querySelector('.stat-value, .stat-value-sm');
        const labelEl = card.querySelector('.stat-label');
        if (valEl) valEl.textContent = stats[i].value.toLocaleString();
        if (labelEl) labelEl.textContent = stats[i].label;
      }
    },

    renderTopArtists(data) {
      const list = document.querySelector('.top-artists-list');
      if (!list) return;
      const artists = data.artists || [];
      const maxPlays = Math.max(...artists.map(a => a.play_count), 1);

      const items = list.querySelectorAll('.top-list-item');
      artists.slice(0, items.length).forEach((a, i) => {
        const item = items[i];
        const nameEl = item.querySelector('.top-list-name');
        const countEl = item.querySelector('.top-list-count');
        const barFill = item.querySelector('.top-list-bar-fill');
        if (nameEl) nameEl.textContent = a.name;
        if (countEl) countEl.textContent = a.play_count.toLocaleString() + ' plays';
        if (barFill) barFill.style.width = ((a.play_count / maxPlays) * 100) + '%';
      });
    },

    renderTopTracks(data) {
      const list = document.querySelector('.top-tracks-list');
      if (!list) return;
      const tracks = data.tracks || [];
      const maxPlays = Math.max(...tracks.map(t => t.play_count), 1);

      const items = list.querySelectorAll('.top-list-item');
      tracks.slice(0, items.length).forEach((t, i) => {
        const item = items[i];
        const nameEl = item.querySelector('.top-list-name');
        const countEl = item.querySelector('.top-list-count');
        const barFill = item.querySelector('.top-list-bar-fill');
        if (nameEl) {
          const name = t.name.length > 40 ? t.name.slice(0, 37) + '…' : t.name;
          nameEl.textContent = name;
        }
        if (countEl) countEl.textContent = t.play_count.toLocaleString() + ' plays';
        if (barFill) {
          barFill.style.width = ((t.play_count / maxPlays) * 100) + '%';
          barFill.classList.toggle('top-list-bar-fill-cyan', true);
        }
      });
    },

    renderGenreCloud(data) {
      const container = document.querySelector('.genre-cloud');
      if (!container) return;
      const tags = container.querySelectorAll('.genre-tag');
      const genres = data.genres || [];
      const sorted = [...genres].sort((a, b) => b.play_count - a.play_count);
      const max = sorted[0]?.play_count || 1;

      tags.forEach((tag, i) => {
        if (i >= sorted.length) { tag.style.display = 'none'; return; }
        const g = sorted[i];
        tag.textContent = g.genre;
        tag.className = 'genre-tag';
        const pct = g.play_count / max;
        if (pct >= 0.6) tag.classList.add('primary');
        else if (pct >= 0.3) tag.classList.add('secondary');
        else if (pct >= 0.15) tag.classList.add('muted');
        else tag.classList.add('faint');
        tag.style.display = '';
      });
    },

    renderGenreFamilies(data) {
      const container = document.querySelector('.genre-families');
      if (!container) return;
      const families = data.families || [];
      const familyEls = container.querySelectorAll('.genre-family');

      familyEls.forEach((el, i) => {
        const f = families[i];
        if (!f) { el.style.display = 'none'; return; }
        el.style.display = '';
        const nameEl = el.querySelector('.genre-family-name');
        const countEl = el.querySelector('.genre-family-count');
        const tagsEl = el.querySelector('.genre-family-tags');
        if (nameEl) nameEl.textContent = f.name;
        if (countEl) countEl.textContent = f.total_plays.toLocaleString() + ' plays';
        if (tagsEl) {
          tagsEl.textContent = '';
          f.genres.forEach((g) => {
            const tag = document.createElement('span');
            tag.className = 'genre-tag secondary';
            tag.textContent = g;
            tagsEl.appendChild(tag);
          });
        }
      });
    },

    renderArchetype(analytics) {
      const nameEl = document.querySelector('.archetype-name');
      const descEl = document.querySelector('.archetype-description');
      if (nameEl) nameEl.textContent = analytics.listener_archetype?.archetype || 'The Listener';
      if (descEl) {
        const signals = analytics.listener_archetype?.archetype_signals || [];
        descEl.textContent = signals.map(s => s.description).filter(Boolean).join('. ') ||
          'Your listener archetype will appear here as data accumulates.';
      }
    },

    renderMusicDNA(analytics) {
      const dna = analytics.music_dna?.dna || {};
      const grid = document.querySelector('.dna-grid');
      if (!grid) return;

      // Map API dimensions to design-system labels
      const dims = [
        { key: 'high_energy_vs_low_energy', label: 'Energetic', val: dna['high_energy_vs_low_energy']?.high_energy, max: 100 },
        { key: 'acoustic_vs_electronic', label: 'Acoustic', val: dna['acoustic_vs_electronic']?.acoustic, max: 100 },
        { key: 'danceability', label: 'Danceable', val: dna['danceability'], max: 100 },
        { key: 'positive_vs_melancholic', label: 'Positive', val: dna['positive_vs_melancholic']?.positive, max: 100 },
        { key: 'tempo', label: 'Tempo', val: dna['tempo'], max: 100 },
        { key: 'loudness', label: 'Loud', val: dna['loudness'], max: 100 },
        { key: 'live', label: 'Live', val: dna['live'], max: 100 },
        { key: 'instrumental', label: 'Instrumental', val: dna['instrumental'], max: 100 },
      ];

      const items = grid.querySelectorAll('.dna-item');
      dims.forEach((dim, i) => {
        if (i >= items.length) return;
        const item = items[i];
        const barFill = item.querySelector('.bar-fill');
        const valEl = item.querySelector('.bar-value');
        const labelEl = item.querySelector('.bar-label');
        if (labelEl) labelEl.textContent = dim.label;
        if (barFill) {
          const pct = Math.min(100, Math.max(0, dim.val ?? 50));
          barFill.style.width = pct + '%';
          barFill.style.background = this.dnaColor(dim.key);
        }
        if (valEl) valEl.textContent = Math.round(pct);
      });
    },

    dnaColor(key) {
      const colors = {
        'high_energy_vs_low_energy': 'var(--accent)',
        'acoustic_vs_electronic': '#22d3ee',
        'danceability': 'var(--accent)',
        'positive_vs_melancholic': '#f59e0b',
        'tempo': 'var(--accent)',
        'loudness': '#ef4444',
        'live': '#22d3ee',
        'instrumental': '#a78bfa',
      };
      return colors[key] || 'var(--accent)';
    },

    /* ===== Taste ===== */
    async loadTaste() {
      try {
        const [genres, analytics] = await Promise.all([
          this.fetchJSON('/api/genres'),
          this.fetchJSON('/api/analytics'),
        ]);
        this.renderGenreFamilies(genres);
        // The diversity block reads genre_diversity, which only /api/analytics
        // carries — passing the genre payload left it reporting 0 genres.
        this.renderDiversityScore(analytics);
        this.renderDiscoveryMeter(analytics);
        this.renderMusicDNA(analytics);
      } catch (e) {
        console.warn('Taste load error:', e);
      }
    },

    renderDiversityScore(data) {
      const scoreEl = document.querySelector('.diversity-value, .diversity-score-value');
      const badgeEl = document.querySelector('.diversity-badge');
      const barEl = document.querySelector('.diversity-bar');
      const captionEl = document.querySelector('.diversity-caption');

      const score = data.genre_diversity?.diversity_score || 0;
      const count = data.genre_diversity?.genre_count || 0;

      if (scoreEl) scoreEl.textContent = score;
      if (badgeEl) {
        badgeEl.textContent = score >= 80 ? 'High diversity' : score >= 50 ? 'Moderate diversity' : 'Low diversity';
      }
      // .diversity-bar is the track; the gradient fill is its child.
      if (barEl) {
        const fill = barEl.firstElementChild;
        if (fill) fill.style.width = score + '%';
        else barEl.style.width = score + '%';
      }
      if (captionEl) {
        const comparison = count >= 15
          ? ' — wider than most listeners, who cluster around 6–10.'
          : count > 0 ? '.' : ' yet.';
        captionEl.textContent = `Across ${count} genre${count === 1 ? '' : 's'}${comparison}`;
      }
    },

    renderDiscoveryMeter(analytics) {
      const discovery = analytics.discovery_rate || {};
      const comfort = discovery.comfort_score || 0;
      const discoveryVal = discovery.discovery_rate || 0;

      const trackEl = document.querySelector('.discovery-meter-track, .discovery-track');
      const comfortEl = document.querySelector('.discovery-comfort');
      const discoveryEl = document.querySelector('.discovery-discovery');
      const captionEl = document.querySelector('.discovery-caption');

      if (trackEl) {
        if (comfortEl) comfortEl.style.width = comfort + '%';
        if (discoveryEl) discoveryEl.style.left = comfort + '%';
      }
      if (captionEl) {
        captionEl.textContent = `${comfort}% of plays are repeat favorites; ${discoveryVal}% are tracks from artists you've followed for under 3 months.`;
      }
    },

    /* ===== Evolution ===== */
    async loadEvolution() {
      try {
        const data = await this.fetchJSON('/api/taste-evolution');
        this.renderEvolutionTimeline(data);
      } catch (e) {
        console.warn('Evolution load error:', e);
      }
    },

    renderEvolutionTimeline(data) {
      const chart = document.querySelector('.evolution-chart');
      if (!chart) return;
      const bars = chart.querySelectorAll('.evolution-bar');

      const timeline = data.timeline || [];
      if (timeline.length === 0) {
        // Show empty state
        const empty = document.querySelector('.evolution-empty');
        if (empty) empty.style.display = 'block';
        bars.forEach(b => b.style.display = 'none');
        return;
      }

      const max = Math.max(...timeline.map(t => t.total_plays), 1);
      // Show the most recent periods when the timeline is longer than the
      // markup, rather than the oldest. Columns are right-aligned so a short
      // history fills the newest slots and leaves empty tracks behind it.
      const shown = timeline.slice(-bars.length);
      const offset = bars.length - shown.length;

      bars.forEach((bar, i) => {
        const t = shown[i - offset];
        const fill = bar.querySelector('.evolution-bar-fill');
        const label = bar.querySelector('.evolution-bar-label');

        // Every column is a full-height track; the fill inside it carries the
        // value. Sizing only the fill left each track at its mock height, so
        // the columns were not comparable.
        bar.style.height = '100%';
        bar.style.display = '';

        if (!t) {
          if (fill) fill.style.height = '0%';
          if (label) label.textContent = '';
          bar.removeAttribute('title');
          return;
        }

        if (fill) fill.style.height = Math.max((t.total_plays / max) * 100, 2) + '%';
        if (label) label.textContent = t.period || '';
        bar.title = `${t.period}: ${t.total_plays} plays`;
      });

      const caption = document.querySelector('.evolution-caption');
      if (caption) {
        const total = timeline.reduce((sum, t) => sum + (t.total_plays || 0), 0);
        caption.textContent =
          `${total.toLocaleString()} plays across ${timeline.length} ` +
          `${timeline.length === 1 ? 'period' : 'periods'}, ${shown[0].period} to ${shown[shown.length - 1].period}.`;
      }

      // The per-column labels replace the static month axis from the mock.
      const axis = document.querySelector('.evolution-axis');
      if (axis) axis.style.display = 'none';
    },

    /* ===== Listening ===== */
    async loadListening() {
      try {
        const [timeOfDay, sessions] = await Promise.all([
          this.fetchJSON('/api/time-of-day'),
          this.fetchJSON('/api/sessions'),
        ]);
        this.renderMusicClock(timeOfDay);
        this.renderWeekBars(timeOfDay);
        this.renderSessions(sessions);
      } catch (e) {
        console.warn('Listening load error:', e);
      }
    },

    renderMusicClock(data) {
      const bars = document.querySelectorAll('.music-clock .clock-bar');
      const hourly = data.hourly || {};

      // Map hour strings to bar indices (0-23)
      const sortedHours = Object.keys(hourly).map(Number).sort((a, b) => a - b);
      const max = Math.max(...Object.values(hourly), 1);

      bars.forEach((bar, i) => {
        const hour = sortedHours[i];
        if (hour === undefined) {
          bar.style.display = 'none';
          return;
        }
        bar.style.display = '';
        const plays = hourly[hour] || 0;
        const pct = (plays / max) * 100;
        bar.style.height = Math.max(4, pct) + '%';
        bar.classList.toggle('accent', pct > 15);
        bar.classList.toggle('half', pct > 8 && pct <= 15);
        bar.classList.toggle('three-quarter', pct > 4 && pct <= 8);
      });

      const caption = document.querySelector('.music-clock-caption');
      if (caption) {
        const peakHour = sortedHours.reduce((best, h) => hourly[h] > (hourly[best] || 0) ? h : best, sortedHours[0]);
        const peakLabel = peakHour >= 0 && peakHour < 12 ? `${peakHour}:00am` :
                          peakHour >= 12 && peakHour < 18 ? `${peakHour-12}:00pm` :
                          `${peakHour}:00pm`;
        caption.textContent = `Peaks ${peakLabel}; near-silent in early hours.`;
      }
    },

    renderWeekBars(data) {
      const bars = document.querySelectorAll('.day-bars .day-bar');
      const days = data.daily || {};
      const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
      const max = Math.max(...Object.values(days), 1);

      bars.forEach((bar, i) => {
        const name = dayNames[i];
        bar.style.height = (days[name] ? ((days[name] / max) * 100) : 5) + '%';
      });
    },

    renderSessions(data) {
      const tbody = document.querySelector('.sessions-table tbody');
      if (!tbody) return;
      const sessions = data.sessions || [];
      const rows = tbody.querySelectorAll('tr');

      sessions.slice(0, rows.length).forEach((s, i) => {
        const row = rows[i];
        if (!row) return;
        const cells = row.querySelectorAll('td');
        if (cells.length >= 4) {
          cells[0].textContent = this.formatSessionTime(s.start);
          cells[1].textContent = s.track_count;
          cells[2].textContent = s.unique_tracks;
          cells[3].textContent = s.unique_artists;
        }
      });
    },

    formatSessionTime(start) {
      if (!start) return '';
      try {
        const d = new Date(start);
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const yesterday = new Date(today.getTime() - 86400000);
        const sessionDate = new Date(d.getFullYear(), d.getMonth(), d.getDate());

        if (sessionDate.getTime() === today.getTime()) {
          return 'Today, ' + this.formatTime(d);
        }
        if (sessionDate.getTime() === yesterday.getTime()) {
          return 'Yesterday, ' + this.formatTime(d);
        }
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ', ' + this.formatTime(d);
      } catch (e) {
        return start;
      }
    },

    formatTime(d) {
      const h = d.getHours();
      const m = d.getMinutes().toString().padStart(2, '0');
      const ampm = h >= 12 ? 'pm' : 'am';
      const hour12 = h % 12 || 12;
      return `${hour12}:${m}${ampm}`;
    },

    /* ===== Library ===== */
    async loadLibrary() {
      try {
        const data = await this.fetchJSON('/api/library');
        this.renderLibraryTabs(data);
      } catch (e) {
        console.warn('Library load error:', e);
      }
    },

    attachLibraryTabs() {
      document.querySelectorAll('.tab-btn:not([data-bound])').forEach((btn) => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => {
          const tab = btn.dataset.tab;
          if (!tab) return;
          this.libraryState = { tab };
          if (this.libraryData) {
            this.renderLibraryContent(tab, this.libraryData);
          } else {
            this.loadLibrary();
          }
        });
      });
    },

    renderLibraryTabs(data) {
      this.libraryData = data;
      // Update tab counts
      const tracksBtn = document.querySelector('.tab-btn[data-tab="tracks"]');
      const albumsBtn = document.querySelector('.tab-btn[data-tab="albums"]');
      const playlistsBtn = document.querySelector('.tab-btn[data-tab="playlists"]');

      if (tracksBtn) tracksBtn.textContent = `Tracks (${data.saved_tracks.length})`;
      if (albumsBtn) albumsBtn.textContent = `Albums (${data.saved_albums.length})`;
      if (playlistsBtn) playlistsBtn.textContent = `Playlists (${data.playlists.length})`;

      // Show active tab content
      const state = this.libraryState || { tab: 'tracks' };
      this.renderLibraryContent(state.tab, data);
    },

    renderLibraryContent(tab, data) {
      this.libraryState = { tab };

      // Clear all tab contents
      document.querySelectorAll('.lib-tracks, .lib-albums, .lib-playlists').forEach(el => el.style.display = 'none');

      if (tab === 'tracks') {
        document.querySelector('.lib-tracks')?.style.setProperty('display', 'block');
        this.renderSavedTracks(data.saved_tracks);
      } else if (tab === 'albums') {
        document.querySelector('.lib-albums')?.style.setProperty('display', 'block');
        this.renderSavedAlbums(data.saved_albums);
      } else if (tab === 'playlists') {
        document.querySelector('.lib-playlists')?.style.setProperty('display', 'block');
        this.renderPlaylists(data.playlists);
      }

      // Update active button styles
      const activeColor = '#1ed760';
      const inactiveColor = '#b3b3b3';
      const activeBg = 'rgba(30,215,96,0.15)';
      const inactiveBg = 'transparent';

      document.querySelectorAll('.tab-btn').forEach(btn => {
        const isActive = btn.dataset.tab === tab;
        btn.style.background = isActive ? activeBg : inactiveBg;
        btn.style.color = isActive ? activeColor : inactiveColor;
        btn.style.fontWeight = isActive ? '700' : '600';
      });
    },

    renderSavedTracks(tracks) {
      const tbody = document.querySelector('.lib-tracks tbody');
      if (!tbody) return;
      const rows = tbody.querySelectorAll('tr');

      tracks.slice(0, rows.length).forEach((t, i) => {
        const row = rows[i];
        if (!row) return;
        const cells = row.querySelectorAll('td');
        if (cells.length >= 5) {
          cells[0].textContent = t.name;
          cells[1].textContent = t.artist;
          cells[2].textContent = t.album;
          cells[3].textContent = this.formatDuration(t.duration_ms);
          cells[4].textContent = t.added_at ? new Date(t.added_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
        }
      });
    },

    renderSavedAlbums(albums) {
      const grid = document.querySelector('.lib-albums .album-grid, .lib-albums-grid');
      if (!grid) return;
      const items = grid.querySelectorAll('.album-item');
      items.forEach((item, i) => {
        const a = albums[i];
        if (!a) { item.style.display = 'none'; return; }
        item.style.display = '';
        const nameEl = item.querySelector('.album-name');
        const metaEl = item.querySelector('.album-meta');
        if (nameEl) nameEl.textContent = a.name;
        if (metaEl) metaEl.textContent = [a.artist, a.release_date].filter(Boolean).join(' · ');
      });
    },

    renderPlaylists(playlists) {
      const grid = document.querySelector('.lib-playlists .playlist-grid, .lib-playlists-grid');
      if (!grid) return;
      const items = grid.querySelectorAll('.playlist-card');

      items.forEach((item, i) => {
        const p = playlists[i];
        if (!p) { item.style.display = 'none'; return; }
        item.style.display = '';
        const nameEl = item.querySelector('.playlist-name');
        const countEl = item.querySelector('.playlist-track-count');
        const badgeEl = item.querySelector('.playlist-badge');
        if (nameEl) nameEl.textContent = p.name;
        if (countEl) countEl.textContent = p.tracks_total + ' tracks';
        if (badgeEl) {
          if (p.collaborative) {
            badgeEl.className = 'playlist-badge collaborative';
            badgeEl.textContent = 'Collaborative';
          } else if (p.public) {
            badgeEl.className = 'playlist-badge public';
            badgeEl.textContent = 'Public';
          } else {
            badgeEl.className = 'playlist-badge private';
            badgeEl.textContent = 'Private';
          }
        }
      });
    },

    formatDuration(ms) {
      if (!ms) return '';
      const min = Math.floor(ms / 60000);
      const sec = Math.floor((ms % 60000) / 1000);
      return `${min}:${sec.toString().padStart(2, '0')}`;
    },

    /* ===== Intelligence ===== */
    async loadIntelligence() {
      try {
        const [data, insights] = await Promise.all([
          this.fetchJSON('/api/analytics'),
          this.fetchJSON('/api/insights').catch(() => null),
        ]);
        this.renderArchetype(data);
        this.renderInsights(data, insights);
        this.renderAnomalies(data);
        this.renderRecommendations(data);
      } catch (e) {
        console.warn('Intelligence load error:', e);
      }
    },

    renderInsights(data, served) {
      const list = document.querySelector('.insights-list');
      if (!list) return;

      // /api/insights derives these server-side; fall back to the local rules
      // when it is unreachable.
      const derived = (served && served.insights && served.insights.length)
        ? served.insights
        : this.deriveInsights(data);

      const cards = list.querySelectorAll('.insight-card');
      cards.forEach((card, i) => {
        if (i >= derived.length) { card.style.display = 'none'; return; }
        card.style.display = '';
        card.textContent = derived[i];
      });
    },

    deriveInsights(data) {
      const list = [];
      const diversity = data.genre_diversity;
      const discovery = data.discovery_rate;
      const archetype = data.listener_archetype;

      if (diversity) {
        list.push(`You span ${diversity.genre_count} genres, with a diversity score of ${diversity.diversity_score}% (Shannon index ${diversity.shannon_index}).`);
      }
      if (discovery && discovery.discovery_rate > 50) {
        list.push(`You discover new music at a ${discovery.discovery_rate}% rate — ${discovery.discovery_score > 70 ? 'well above' : 'above'} average. Your listening is actively expanding.`);
      }
      if (archetype && archetype.archetype !== 'The Listener') {
        list.push(`Your archetype is "${archetype.archetype}" — ${archetype.archetype_signals?.map(s => s.description).join('; ')}.`);
      }
      if (data.explicit_content && data.explicit_content.explicit_percentage > 50) {
        list.push(`Over half your listening is explicit content — a notable signal in your taste profile.`);
      }
      if (data.mainstream_vs_obscure && data.mainstream_vs_obscure.tendency === 'obscure/underground') {
        list.push(`Your listening leans obscure/underground — you gravitate toward lesser-known artists over mainstream hits.`);
      }
      if (list.length === 0) {
        list.push('Your listening patterns are still forming. Insights will appear as more data accumulates.');
      }
      return list;
    },

    renderAnomalies(data) {
      const list = document.querySelector('.anomalies-list');
      if (!list) return;

      const anomalies = data.anomalies?.findings || [];
      const cards = list.querySelectorAll('.anomaly-card');

      anomalies.slice(0, cards.length).forEach((a, i) => {
        const card = cards[i];
        if (!card) return;
        const icon = card.querySelector('.anomaly-icon');
        const title = card.querySelector('.anomaly-title');
        const desc = card.querySelector('.anomaly-description');
        if (icon) {
          const svg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="1.8" style="flex:0 0 auto;margin-top:2px"><path d="M12 3l10 18H2z"/><path d="M12 9v5"/><path d="M12 17h.01"/></svg>`;
          icon.innerHTML = svg;
        }
        if (title) {
          title.textContent = a.title
            || (a.type ? a.type.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase()) : 'Anomaly');
        }
        if (desc) desc.textContent = a.description || '';
      });

      // Hide extra cards
      for (let i = anomalies.length; i < cards.length; i++) {
        cards[i].style.display = 'none';
      }
    },

    renderRecommendations(data) {
      const list = document.querySelector('.recommendations-list');
      if (!list) return;

      const recs = data.recommendations?.recommendations || [];
      const cards = list.querySelectorAll('.recommendation-card');

      recs.slice(0, cards.length).forEach((r, i) => {
        const card = cards[i];
        if (!card) return;
        const nameEl = card.querySelector('.recommendation-name');
        const reasonEl = card.querySelector('.recommendation-reason');
        const tagEl = card.querySelector('.recommendation-tag');
        if (nameEl) nameEl.textContent = r.to_genre || r.artist_name || 'Recommendation';
        if (reasonEl) reasonEl.textContent = r.reason || '';
        if (tagEl) {
          tagEl.textContent = r.type === 'genre_expansion' ? 'Genre' : 'Artist';
        }
      });

      // Hide extra cards
      for (let i = recs.length; i < cards.length; i++) {
        cards[i].style.display = 'none';
      }
    },

    /* ===== Recent activity (Live page) ===== */
    async loadRecentActivity() {
      if (!document.querySelector('.activity-list')) return;
      try {
        const data = await this.fetchJSON('/api/recent?limit=20');
        this.renderRecentActivity(data.plays || []);
      } catch (e) {
        console.warn('Recent activity load error:', e);
      }
    },

    renderRecentActivity(plays) {
      const items = document.querySelectorAll('.activity-list .activity-item');
      items.forEach((item, i) => {
        const play = plays[i];
        if (!play) { item.style.display = 'none'; return; }
        item.style.display = '';

        const track = item.querySelector('.activity-track');
        const artist = item.querySelector('.activity-artist');
        const time = item.querySelector('.activity-time');
        const ago = item.querySelector('.activity-ago');

        if (track) track.textContent = play.track || '';
        if (artist) artist.textContent = play.artist ? `— ${play.artist}` : '';
        if (time) time.textContent = this.formatTimestamp(play.played_at);
        if (ago) {
          ago.textContent = play.tracks_ago === 0
            ? 'most recent'
            : `${play.tracks_ago} track${play.tracks_ago === 1 ? '' : 's'} ago`;
        }
      });
    },

    /* ===== Settings ===== */
    async loadSettings() {
      if (!document.querySelector('.settings-status')) return;
      try {
        const status = await this.fetchJSON('/api/status');
        this.renderSettingsStatus(status);
      } catch (e) {
        console.warn('Settings load error:', e);
      }
    },

    renderSettingsStatus(status) {
      const counts = status.counts || {};
      const set = (selector, value) => {
        const el = document.querySelector(selector);
        if (el) el.textContent = value;
      };

      set('.status-plays', (counts.plays || 0).toLocaleString());
      set('.status-artists', (counts.artists || 0).toLocaleString());
      set('.status-tracks', (counts.tracks || 0).toLocaleString());
      set('.status-saved', ((counts.saved_tracks || 0) + (counts.saved_albums || 0)).toLocaleString());
      set('.status-playlists', (counts.playlists || 0).toLocaleString());
      set('.status-db-size', this.formatBytes(status.database_bytes));
      set('.status-last-play', this.formatTimestamp(status.last_play));
      set('.status-analytics', status.analytics_cached
        ? this.formatTimestamp(status.analytics_computed_at)
        : 'Never — run analytics.py --cache');
    },

    formatBytes(bytes) {
      if (!bytes) return '—';
      const units = ['B', 'KB', 'MB', 'GB'];
      let value = bytes;
      let unit = 0;
      while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
      return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
    },

    formatTimestamp(iso) {
      if (!iso) return '—';
      const date = new Date(iso);
      if (isNaN(date.getTime())) return '—';
      return date.toLocaleString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
    },

    /* ===== Live ===== */
    startLivePolling() {
      if (this.liveInterval) clearInterval(this.liveInterval);
      this.liveInterval = setInterval(() => this.refreshLive(), 5000);
      this.refreshLive();
    },

    async refreshLive() {
      try {
        const data = await this.fetchJSON('/api/currently-playing');
        this.renderLive(data);
      } catch (e) {
        console.warn('Live refresh error:', e);
      }
    },

    renderLive(data) {
      const statusDot = document.querySelector('.live-dot, .live-status-dot');
      const statusText = document.querySelector('.live-status-text');
      const trackName = document.querySelector('.live-track-name');
      const trackArtist = document.querySelector('.live-artist, .live-track-artist');
      const progressFill = document.querySelector('.live-progress-fill');
      const currentTimeEl = document.querySelector('.live-current-time');
      const totalTimeEl = document.querySelector('.live-total-time');
      const progressTrack = document.querySelector('.live-progress-track');
      const audioFeatures = document.querySelector('.audio-features-grid');

      if (data.playing && data.track) {
        if (statusDot) {
          statusDot.className = 'live-dot';
          statusDot.style.background = 'var(--accent)';
        }
        if (statusText) statusText.innerHTML = '<span class="live-dot" style="width:8px;height:8px;border-radius:50%;background:#1ed760;display:inline-block"></span>Now playing — auto-refreshing every 5s';

        if (trackName) trackName.textContent = data.track.name;
        if (trackArtist) trackArtist.textContent = data.track.artist + ' — ' + data.track.album;

        // progress_ms sits beside `track` in the response, not inside it.
        const progressMs = data.progress_ms || 0;
        if (progressTrack && data.track.duration_ms > 0) {
          const pct = Math.min(100, (progressMs / data.track.duration_ms) * 100);
          if (progressFill) progressFill.style.width = pct + '%';
          if (currentTimeEl) currentTimeEl.textContent = this.formatDuration(progressMs);
          if (totalTimeEl) totalTimeEl.textContent = this.formatDuration(data.track.duration_ms);
        }

        // Audio features
        if (audioFeatures) {
          const features = data.audio_features || {};
          const dims = [
            { label: 'Danceability', val: features.danceability, unit: '' },
            { label: 'Energy', val: features.energy, unit: '' },
            { label: 'Valence', val: features.valence, unit: '' },
            { label: 'Acousticness', val: features.acousticness, unit: '' },
            { label: 'Tempo', val: features.tempo, unit: ' BPM' },
            { label: 'Loudness', val: features.loudness, unit: ' dB' },
          ];
          const items = audioFeatures.querySelectorAll('.audio-feature');
          dims.forEach((dim, i) => {
            if (i >= items.length) return;
            const item = items[i];
            const labelEl = item.querySelector('.bar-label');
            const barFill = item.querySelector('.bar-fill');
            const valEl = item.querySelector('.bar-value');
            if (labelEl) labelEl.textContent = dim.label;
            const pct = dim.val != null ? Math.min(100, Math.max(0, (dim.val * 100))) : 50;
            if (barFill) {
              barFill.style.width = pct + '%';
              barFill.style.background = this.liveDnaColor(dim.label);
            }
            if (valEl) valEl.textContent = (dim.val != null ? (dim.label === 'Tempo' ? Math.round(dim.val) : dim.val.toFixed(2)) : '—') + dim.unit;
          });
        }
      } else {
        if (statusDot) {
          statusDot.className = 'live-dot';
          statusDot.style.background = 'var(--text-dim)';
        }
        if (statusText) statusText.innerHTML = '<span style="width:8px;height:8px;border-radius:50%;background:#777;display:inline-block;margin-right:7px"></span>Not playing right now';
        if (trackName) trackName.textContent = 'Nothing playing';
        if (trackArtist) trackArtist.textContent = '';
        if (progressTrack) progressTrack.style.display = 'none';
        if (audioFeatures) {
          audioFeatures.querySelectorAll('.audio-feature').forEach(item => {
            const barValue = item.querySelector('.bar-value');
            if (barValue) barValue.textContent = '—';
          });
        }
      }
    },

    liveDnaColor(label) {
      const colors = {
        'Danceability': 'var(--accent)',
        'Energy': '#ef4444',
        'Valence': '#f59e0b',
        'Acousticness': '#22d3ee',
        'Tempo': 'var(--accent)',
        'Loudness': '#ef4444',
      };
      return colors[label] || 'var(--accent)';
    },

    /* ===== Auth Callback ===== */
    attachAuthCallbackSteps() {
      const steps = document.querySelectorAll('.auth-step');
      if (steps.length === 0) return;

      const msgs = [
        'Authenticated with Spotify',
        'Fetched your profile',
        'Syncing recent listening & library…',
        'Computing analytics',
      ];

      steps.forEach((step, i) => {
        const icon = step.querySelector('svg');
        const text = step.querySelector('.auth-step-text');

        // Mark first two as done immediately
        if (i < 2) {
          if (icon) {
            icon.style.stroke = 'var(--accent)';
            icon.style.opacity = '1';
          }
          if (text) text.textContent = msgs[i];
          step.classList.remove('auth-step-pending');
          step.classList.add('auth-step-done');
        } else if (i === 2) {
          // Third step is the "syncing" one — pulse it
          if (icon) {
            icon.style.stroke = 'var(--accent)';
            icon.classList.add('pulse-dot');
          }
          if (text) text.textContent = msgs[i];
          step.classList.remove('auth-step-pending');
          step.classList.add('auth-step-done');
        } else {
          // Last step — pending
          if (icon) {
            icon.style.stroke = 'var(--text-dim)';
          }
          if (text) text.textContent = msgs[i];
        }
      });

      // Simulate sync completion after 3 seconds
      setTimeout(() => {
        const steps2 = document.querySelectorAll('.auth-step');
        if (steps2.length >= 4) {
          const lastStep = steps2[3];
          const lastIcon = lastStep?.querySelector('svg');
          const lastText = lastStep?.querySelector('.auth-step-text');
          if (lastIcon) {
            lastIcon.style.stroke = 'var(--accent)';
            lastIcon.classList.remove('pulse-dot');
          }
          if (lastText) lastText.textContent = 'Analytics computed — you\'re all set';
        }

        // Navigate to Overview after a brief delay
        setTimeout(() => {
          window.location.href = 'Overview.dc.html';
        }, 800);
      }, 3000);
    },

    /* ===== Helpers ===== */
    async fetchJSON(url) {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      return res.json();
    },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => App.init());
  } else {
    App.init();
  }
})();
