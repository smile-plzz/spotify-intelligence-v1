// ============================================================
// Spotify Intelligence Dashboard — Client-side JS
// ============================================================

const App = {
  charts: {},
  currentlyPlayingInterval: null,

  init() {
    this.bindNavigation();
    this.loadOverview();
    this.startLivePolling();
  },

  bindNavigation() {
    document.querySelectorAll('.nav-links a').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const target = link.getAttribute('href').slice(1);
        this.navigateTo(target);
      });
    });
  },

  navigateTo(sectionId) {
    document.querySelectorAll('.nav-links a').forEach(a => a.classList.remove('active'));
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));

    document.querySelector(`.nav-links a[href="#${sectionId}"]`).classList.add('active');
    document.getElementById(sectionId).classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Load section data if needed
    if (sectionId === 'taste') this.loadGenres();
    if (sectionId === 'evolution') this.loadTasteEvolution();
    if (sectionId === 'listening') this.loadListeningPatterns();
    if (sectionId === 'library') this.loadLibrary();
    if (sectionId === 'intelligence') this.loadIntelligence();
  },

  // ===== Overview =====
  async loadOverview() {
    try {
      const [summary, artists, tracks] = await Promise.all([
        this.fetchJSON('/api/summary'),
        this.fetchJSON('/api/top-artists'),
        this.fetchJSON('/api/top-tracks'),
      ]);

      this.renderStats(summary);
      this.renderCurrentlyPlaying(summary);
      this.renderTopArtistsChart(artists);
      this.renderTopTracksChart(tracks);
      this.renderGenreCloud();
      this.loadArchetype();
      this.loadDNAMetrics();
    } catch (err) {
      console.error('Failed to load overview:', err);
    }
  },

  renderStats(summary) {
    document.getElementById('stat-total-plays').textContent = summary.total_plays.toLocaleString();
    document.getElementById('stat-unique-artists').textContent = summary.unique_artists.toLocaleString();
    document.getElementById('stat-unique-tracks').textContent = summary.unique_tracks.toLocaleString();
    document.getElementById('stat-unique-albums').textContent = summary.unique_albums.toLocaleString();
  },

  renderCurrentlyPlaying(summary) {
    const placeholder = document.getElementById('now-playing-placeholder');
    const content = document.getElementById('now-playing-content');

    if (summary.currently_playing) {
      placeholder.style.display = 'none';
      content.style.display = 'flex';

      document.getElementById('np-artist').textContent = summary.currently_playing.artist;
      document.getElementById('np-track').textContent = summary.currently_playing.name;
      document.getElementById('np-album').textContent = summary.currently_playing.album || 'Unknown album';

      const progress = summary.currently_playing.progress_ms || 0;
      const duration = summary.currently_playing.duration_ms || 1;
      const pct = Math.min(100, (progress / duration) * 100);
      document.getElementById('np-progress-fill').style.width = pct + '%';
      document.getElementById('np-current').textContent = this.formatTime(progress);
      document.getElementById('np-total').textContent = this.formatTime(duration);
    }
  },

  renderTopArtistsChart(data) {
    const ctx = document.getElementById('top-artists-chart').getContext('2d');
    const artists = data.artists.slice(0, 10).reverse();

    this.destroyChart('top-artists-chart');
    this.charts['top-artists-chart'] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: artists.map(a => a.name),
        datasets: [{
          data: artists.map(a => a.play_count),
          backgroundColor: artists.map((_, i) => this.chartColor(i, 10)),
          borderColor: 'transparent',
          borderRadius: 4,
          barPercentage: 0.7,
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1a1a24',
            titleColor: '#e8e8f0',
            bodyColor: '#a0a0b8',
            borderColor: '#2a2a3a',
            borderWidth: 1,
            callbacks: {
              label: (ctx) => `${ctx.raw} plays`,
            }
          }
        },
        scales: {
          x: {
            grid: { color: '#2a2a3a', drawBorder: false },
            ticks: { color: '#6a6a80' },
          },
          y: {
            grid: { display: false },
            ticks: { color: '#a0a0b8', font: { size: 11 } },
          }
        }
      }
    });
  },

  renderTopTracksChart(data) {
    const ctx = document.getElementById('top-tracks-chart').getContext('2d');
    const tracks = data.tracks.slice(0, 10).reverse();

    this.destroyChart('top-tracks-chart');
    this.charts['top-tracks-chart'] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: tracks.map(t => t.name.length > 20 ? t.name.slice(0, 18) + '...' : t.name),
        datasets: [{
          data: tracks.map(t => t.play_count || 1),
          backgroundColor: tracks.map((_, i) => this.chartColor(i, 10)),
          borderColor: 'transparent',
          borderRadius: 4,
          barPercentage: 0.7,
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1a1a24',
            titleColor: '#e8e8f0',
            bodyColor: '#a0a0b8',
            borderColor: '#2a2a3a',
            borderWidth: 1,
            callbacks: {
              afterLabel: (ctx) => `by ${tracks[ctx.dataIndex].artist}`,
            }
          }
        },
        scales: {
          x: {
            grid: { color: '#2a2a3a', drawBorder: false },
            ticks: { color: '#6a6a80' },
          },
          y: {
            grid: { display: false },
            ticks: { color: '#a0a0b8', font: { size: 11 } },
          }
        }
      }
    });
  },

  renderGenreCloud() {
    // Static preview — will be replaced by real data when /api/genres is loaded
    const cloud = document.getElementById('genre-cloud');
    const previewGenres = ['Alternative', 'Rock', 'Indie Rock', 'Metal', 'Folk', 'Pop', 'Electronic', 'Hip-Hop'];
    cloud.innerHTML = previewGenres.map(g =>
      `<span class="genre-tag primary">${g}</span>`
    ).join('');
  },

  async loadArchetype() {
    try {
      // Load from analytics cache
      const analytics = await this.fetchJSON('/api/analytics');
      const arch = analytics.listener_archetype;

      document.getElementById('archetype-name').textContent = arch.archetype;
      document.getElementById('archetype-signals').innerHTML = arch.archetype_signals.map(s =>
        `<div>• ${s.description}</div>`
      ).join('');
    } catch (err) {
      document.getElementById('archetype-name').textContent = 'The Listener';
      document.getElementById('archetype-signals').innerHTML = '<p>Your archetype will appear here as data accumulates.</p>';
    }
  },

  async loadDNAMetrics() {
    try {
      const analytics = await this.fetchJSON('/api/analytics');
      const dna = analytics.music_dna.dna;

      const grid = document.getElementById('dna-grid');
      grid.innerHTML = Object.entries(dna).map(([key, dim]) => {
        if (!dim.label) return '';
        const val = dim.indie ?? dim.discovery ?? dim.new ?? dim.focused ?? dim.loyal ?? dim.high_energy ?? dim.acoustic ?? dim.positive ?? 50;
        const isLeft = key.includes('indie') || key.includes('discovery') || key.includes('new') || key.includes('focused') || key.includes('loyal') || key.includes('high_energy') || key.includes('acoustic') || key.includes('positive');
        const barPct = Math.min(100, Math.max(0, val));
        const color = this.dnaColor(key);

        return `
          <div class="dna-item">
            <div class="dna-dimension">${key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</div>
            <div class="dna-label">${dim.label}</div>
            <div class="dna-bar-bg">
              <div class="dna-bar-fill" style="width:${barPct}%;background:${color}"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-3);margin-top:4px">
              <span>${Math.round(isLeft ? barPct : 100 - barPct)}%</span>
              <span>${Math.round(isLeft ? 100 - barPct : barPct)}%</span>
            </div>
          </div>
        `;
      }).join('');
    } catch (err) {
      document.getElementById('dna-grid').innerHTML = '<p class="empty-state">DNA metrics will appear here.</p>';
    }
  },

  dnaColor(key) {
    const map = {
      indie_vs_mainstream: '#1db954',
      discovery_vs_familiarity: '#3b82f6',
      old_vs_new: '#f59e0b',
      genre_focused_vs_diverse: '#8b5cf6',
      artist_loyal_vs_exploratory: '#ec4899',
      album_listener_vs_singles: '#06b6d4',
      high_energy_vs_low_energy: '#f97316',
      acoustic_vs_electronic: '#22c55e',
      positive_vs_melancholic: '#a855f7',
    };
    return map[key] || '#1db954';
  },

  chartColor(index, total) {
    const hue = (index / total) * 120 + 120; // Green to blue range
    return `hsl(${hue}, 60%, 45%)`;
  },

  // ===== Genres =====
  async loadGenres() {
    try {
      const data = await this.fetchJSON('/api/genres');

      document.getElementById('genre-count-badge').textContent = `${data.total_genres} genres`;

      this.destroyChart('genre-chart');
      const ctx = document.getElementById('genre-chart').getContext('2d');

      const topGenres = data.genres.slice(0, 15).reverse();
      this.charts['genre-chart'] = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: topGenres.map(g => g.genre),
          datasets: [{
            data: topGenres.map(g => g.play_count),
            backgroundColor: topGenres.map((_, i) => this.chartColor(i, 15)),
            borderColor: 'transparent',
            borderRadius: 4,
            barPercentage: 0.7,
          }]
        },
        options: {
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { backgroundColor: '#1a1a24', titleColor: '#e8e8f0', bodyColor: '#a0a0b8', borderColor: '#2a2a3a', borderWidth: 1 }
          },
          scales: {
            x: { grid: { color: '#2a2a3a', drawBorder: false }, ticks: { color: '#6a6a80' } },
            y: { grid: { display: false }, ticks: { color: '#a0a0b8', font: { size: 11 } } }
          }
        }
      });

      // Genre families
      const familiesEl = document.getElementById('genre-families');
      familiesEl.innerHTML = data.families.map(f => `
        <div class="genre-family">
          <div class="genre-family-name">${f.name}</div>
          <div class="genre-family-count">${f.total_plays.toLocaleString()} plays · ${f.total_tracks} tracks</div>
          <div class="genre-family-genres">${f.genres.slice(0, 6).join(', ')}${f.genres.length > 6 ? '...' : ''}</div>
        </div>
      `).join('');

      // Update genre cloud
      const cloud = document.getElementById('genre-cloud');
      const top10 = data.genres.slice(0, 10);
      cloud.innerHTML = top10.map((g, i) =>
        `<span class="genre-tag ${i === 0 ? 'primary' : ''}">${g.genre}</span>`
      ).join('');

    } catch (err) {
      console.error('Failed to load genres:', err);
    }
  },

  // ===== Taste Evolution =====
  async loadTasteEvolution() {
    try {
      const data = await this.fetchJSON('/api/taste-evolution');

      this.destroyChart('timeline-chart');
      const ctx = document.getElementById('timeline-chart').getContext('2d');

      const timeline = data.timeline;
      this.charts['timeline-chart'] = new Chart(ctx, {
        type: 'line',
        data: {
          labels: timeline.map(t => t.period),
          datasets: [
            {
              label: 'Plays',
              data: timeline.map(t => t.plays),
              borderColor: '#1db954',
              backgroundColor: 'rgba(29, 185, 84, 0.1)',
              fill: true,
              tension: 0.3,
              pointRadius: 3,
              pointBackgroundColor: '#1db954',
            },
            {
              label: 'Unique Artists',
              data: timeline.map(t => t.unique_artists),
              borderColor: '#3b82f6',
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              fill: true,
              tension: 0.3,
              pointRadius: 3,
              pointBackgroundColor: '#3b82f6',
              yAxisID: 'y1',
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: {
              labels: { color: '#a0a0b8', usePointStyle: true, padding: 20 }
            },
            tooltip: { backgroundColor: '#1a1a24', titleColor: '#e8e8f0', bodyColor: '#a0a0b8', borderColor: '#2a2a3a', borderWidth: 1 }
          },
          scales: {
            x: { grid: { color: '#2a2a3a' }, ticks: { color: '#6a6a80', maxTicksLimit: 12 } },
            y: { grid: { color: '#2a2a3a' }, ticks: { color: '#6a6a80' }, beginAtZero: true },
            y1: { position: 'right', grid: { display: false }, ticks: { color: '#6a6a80' }, beginAtZero: true }
          }
        }
      });

      // Genre evolution chart
      this.destroyChart('genre-evolution-chart');
      const ctx2 = document.getElementById('genre-evolution-chart').getContext('2d');

      if (timeline.length > 1) {
        const periods = timeline.map(t => t.period);
        const genreSet = [...new Set(timeline.flatMap(t => t.top_genre || []))].slice(0, 5);

        this.charts['genre-evolution-chart'] = new Chart(ctx2, {
          type: 'line',
          data: {
            labels: periods,
            datasets: genreSet.map((genre, i) => ({
              label: genre,
              data: timeline.map(t => t.top_genre === genre ? t.top_genre_plays : 0),
              borderColor: this.chartColor(i, genreSet.length),
              tension: 0.3,
              pointRadius: 2,
              fill: false,
            }))
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { labels: { color: '#a0a0b8', usePointStyle: true, padding: 12, font: { size: 10 } } },
              tooltip: { backgroundColor: '#1a1a24', titleColor: '#e8e8f0', bodyColor: '#a0a0b8', borderColor: '#2a2a3a', borderWidth: 1 }
            },
            scales: {
              x: { grid: { color: '#2a2a3a' }, ticks: { color: '#6a6a80', maxTicksLimit: 10 } },
              y: { grid: { color: '#2a2a3a' }, ticks: { color: '#6a6a80' }, beginAtZero: true }
            }
          }
        });
      }

      // Eras
      const erasEl = document.getElementById('eras-list');
      if (timeline.length > 0) {
        const first = timeline[0];
        const last = timeline[timeline.length - 1];
        erasEl.innerHTML = `
          <div class="archetype-card" style="margin-bottom:12px">
            <div class="card-content archetype-content">
              <div class="archetype-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
              </div>
              <div class="archetype-text">
                <div class="archetype-label">First Recorded Period</div>
                <div class="archetype-name" style="font-size:18px">${first.period}</div>
                <div class="archetype-signals">${first.plays} plays · ${first.unique_artists} artists · Top genre: ${first.top_genre || 'N/A'}</div>
              </div>
            </div>
          </div>
          <div class="archetype-card">
            <div class="card-content archetype-content">
              <div class="archetype-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
              </div>
              <div class="archetype-text">
                <div class="archetype-label">Most Recent Period</div>
                <div class="archetype-name" style="font-size:18px">${last.period}</div>
                <div class="archetype-signals">${last.plays} plays · ${last.unique_artists} artists · Top genre: ${last.top_genre || 'N/A'}</div>
              </div>
            </div>
          </div>
        `;
      }

      // Shifts
      const shiftsEl = document.getElementById('shifts-list');
      const analytics = await this.fetchJSON('/api/analytics');
      const shifts = analytics.taste_evolution?.shifts || [];

      if (shifts.length > 0) {
        const shiftHtml = shifts.map(s => {
          const isGenreShift = s.type === 'genre_shift';
          const desc = isGenreShift
            ? 'Your dominant genre shifted from <strong>' + s.from_genre + '</strong> (' + s.from_period + ') to <strong>' + s.to_genre + '</strong> (' + s.to_period + ')'
            : 'Genre diversity ' + s.direction + ' by ' + s.change + '% between ' + s.from_period + ' and ' + s.to_period;
          return '<div class="card" style="margin-bottom:8px;background:var(--bg-2);border-color:var(--warn)">' +
            '<div class="card-content">' +
            '<div class="anomaly-type">' + s.type.replace(/_/g, ' ').replace(/\b\w/g, function(l){ return l.toUpperCase(); }) + '</div>' +
            '<div class="anomaly-text">' + desc + '</div>' +
            '</div></div>';
        }).join('');
        shiftsEl.innerHTML = shiftHtml;
      } else {
        shiftsEl.innerHTML = '<p class="empty-state">No significant shifts detected in the current data range. More listening data will reveal taste evolution.</p>';
      }

    } catch (err) {
      console.error('Failed to load taste evolution:', err);
    }
  },

  // ===== Listening Patterns =====
  async loadListeningPatterns() {
    try {
      const [timeOfDay, sessions] = await Promise.all([
        this.fetchJSON('/api/time-of-day'),
        this.fetchJSON('/api/sessions'),
      ]);

      // Hourly chart
      this.destroyChart('hourly-chart');
      const ctx = document.getElementById('hourly-chart').getContext('2d');
      const hourly = timeOfDay.hourly;
      const labels = Object.keys(hourly).map(h => `${parseInt(h) % 12 || 12}${parseInt(h) < 12 ? 'am' : 'pm'}`);
      const values = Object.values(hourly);

      this.charts['hourly-chart'] = new Chart(ctx, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            data: values,
            backgroundColor: values.map(v => v > 0 ? 'rgba(29, 185, 84, 0.6)' : 'rgba(29, 185, 84, 0.1)'),
            borderColor: 'transparent',
            borderRadius: 4,
            barPercentage: 0.8,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { backgroundColor: '#1a1a24', titleColor: '#e8e8f0', bodyColor: '#a0a0b8', borderColor: '#2a2a3a', borderWidth: 1 }
          },
          scales: {
            x: { grid: { color: '#2a2a3a' }, ticks: { color: '#6a6a80', maxTicksLimit: 12, font: { size: 10 } } },
            y: { grid: { color: '#2a2a3a' }, ticks: { color: '#6a6a80' }, beginAtZero: true }
          }
        }
      });

      // Clock visual
      this.renderClock(timeOfDay);

      // Day of week
      this.destroyChart('daily-chart');
      const ctx2 = document.getElementById('daily-chart').getContext('2d');
      const days = Object.entries(timeOfDay.daily).sort((a, b) => {
        const order = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        return order.indexOf(a[0]) - order.indexOf(b[0]);
      });
      const dayLabels = days.map(d => d[0].slice(0, 3));
      const dayValues = days.map(d => d[1]);

      this.charts['daily-chart'] = new Chart(ctx2, {
        type: 'bar',
        data: {
          labels: dayLabels,
          datasets: [{
            data: dayValues,
            backgroundColor: dayValues.map((_, i) => {
              const day = days[i][0];
              return (day === 'Saturday' || day === 'Sunday') ? 'rgba(245, 158, 11, 0.6)' : 'rgba(29, 185, 84, 0.6)';
            }),
            borderColor: 'transparent',
            borderRadius: 4,
            barPercentage: 0.6,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { backgroundColor: '#1a1a24', titleColor: '#e8e8f0', bodyColor: '#a0a0b8', borderColor: '#2a2a3a', borderWidth: 1 }
          },
          scales: {
            x: { grid: { color: '#2a2a3a' }, ticks: { color: '#6a6a80' } },
            y: { grid: { color: '#2a2a3a' }, ticks: { color: '#6a6a80' }, beginAtZero: true }
          }
        }
      });

      // Time zones
      const total = Object.values(timeOfDay.hourly).reduce((a, b) => a + b, 0);
      const morning = Object.values(timeOfDay.hourly).filter((_, i) => i >= 6 && i < 12).reduce((a, b) => a + b, 0);
      const afternoon = Object.values(timeOfDay.hourly).filter((_, i) => i >= 12 && i < 18).reduce((a, b) => a + b, 0);
      const evening = Object.values(timeOfDay.hourly).filter((_, i) => i >= 18 && i < 22).reduce((a, b) => a + b, 0);
      const lateNight = Object.values(timeOfDay.hourly).filter((_, i) => i < 6 || i >= 22).reduce((a, b) => a + b, 0);

      document.getElementById('time-zones').innerHTML = `
        <div class="time-zone">
          <div class="tz-name">Morning</div>
          <div class="tz-value">${Math.round(morning / total * 100)}%</div>
          <div class="tz-sub">${morning} plays</div>
        </div>
        <div class="time-zone">
          <div class="tz-name">Afternoon</div>
          <div class="tz-value">${Math.round(afternoon / total * 100)}%</div>
          <div class="tz-sub">${afternoon} plays</div>
        </div>
        <div class="time-zone">
          <div class="tz-name">Evening</div>
          <div class="tz-value">${Math.round(evening / total * 100)}%</div>
          <div class="tz-sub">${evening} plays</div>
        </div>
        <div class="time-zone">
          <div class="tz-name">Late Night</div>
          <div class="tz-value">${Math.round(lateNight / total * 100)}%</div>
          <div class="tz-sub">${lateNight} plays</div>
        </div>
      `;

      // Sessions
      document.getElementById('session-count-badge').textContent = `${sessions.sessions.length} sessions`;

      const lastSessions = sessions.sessions.slice(0, 5);
      if (lastSessions.length > 0) {
        const avgDuration = lastSessions.reduce((s, ses) => s + (ses.track_count * 3.5), 0) / lastSessions.length;
        const avgTracks = lastSessions.reduce((s, ses) => s + ses.track_count, 0) / lastSessions.length;

        document.getElementById('session-stats').innerHTML = `
          <div class="session-stat">
            <div class="session-stat-value">${sessions.sessions.length}</div>
            <div class="session-stat-label">Total Sessions</div>
          </div>
          <div class="session-stat">
            <div class="session-stat-value">${Math.round(avgDuration)}m</div>
            <div class="session-stat-label">Avg Session</div>
          </div>
          <div class="session-stat">
            <div class="session-stat-value">${Math.round(avgTracks)}</div>
            <div class="session-stat-label">Avg Tracks/Session</div>
          </div>
        `;

        this.destroyChart('session-chart');
        const ctx3 = document.getElementById('session-chart').getContext('2d');
        const sessionData = lastSessions.reverse();
        this.charts['session-chart'] = new Chart(ctx3, {
          type: 'bar',
          data: {
            labels: sessionData.map(s => s.start.slice(0, 16)),
            datasets: [
              {
                label: 'Tracks',
                data: sessionData.map(s => s.track_count),
                backgroundColor: 'rgba(29, 185, 84, 0.7)',
                borderColor: 'transparent',
                borderRadius: 4,
                barPercentage: 0.5,
              },
              {
                label: 'Unique Artists',
                data: sessionData.map(s => s.unique_artists),
                backgroundColor: 'rgba(59, 130, 246, 0.7)',
                borderColor: 'transparent',
                borderRadius: 4,
                barPercentage: 0.5,
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { labels: { color: '#a0a0b8', usePointStyle: true } },
              tooltip: { backgroundColor: '#1a1a24', titleColor: '#e8e8f0', bodyColor: '#a0a0b8', borderColor: '#2a2a3a', borderWidth: 1 }
            },
            scales: {
              x: { grid: { color: '#2a2a3a' }, ticks: { color: '#6a6a80', maxTicksLimit: 8, font: { size: 9 } } },
              y: { grid: { color: '#2a2a3a' }, ticks: { color: '#6a6a80' }, beginAtZero: true }
            }
          }
        });
      }

    } catch (err) {
      console.error('Failed to load listening patterns:', err);
    }
  },

  renderClock(timeOfDay) {
    const hourly = timeOfDay.hourly;
    const max = Math.max(...Object.values(hourly), 1);

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 200 200');
    svg.setAttribute('width', '180');
    svg.setAttribute('height', '180');

    // Clock face
    const face = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    face.setAttribute('cx', '100');
    face.setAttribute('cy', '100');
    face.setAttribute('r', '90');
    face.setAttribute('fill', 'var(--bg-2)');
    face.setAttribute('stroke', 'var(--border)');
    face.setAttribute('stroke-width', '2');
    svg.appendChild(face);

    // Hour markers
    for (let h = 0; h < 24; h++) {
      const angle = (h / 24) * 360 - 90;
      const rad = (angle * Math.PI) / 180;
      const innerR = 75;
      const outerR = h % 6 === 0 ? 85 : 80;
      const x1 = 100 + innerR * Math.cos(rad);
      const y1 = 100 + innerR * Math.sin(rad);
      const x2 = 100 + outerR * Math.cos(rad);
      const y2 = 100 + outerR * Math.sin(rad);

      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', x1);
      line.setAttribute('y1', y1);
      line.setAttribute('x2', x2);
      line.setAttribute('y2', y2);
      const intensity = (hourly[h.toString()] || 0) / max;
      const color = `rgba(29, 185, 84, ${0.1 + intensity * 0.8})`;
      line.setAttribute('stroke', color);
      line.setAttribute('stroke-width', h % 6 === 0 ? '2' : '1');
      svg.appendChild(line);
    }

    // Active hour highlight
    let maxHour = 0;
    let maxVal = 0;
    for (let h = 0; h < 24; h++) {
      if ((hourly[h.toString()] || 0) > maxVal) {
        maxVal = hourly[h.toString()] || 0;
        maxHour = h;
      }
    }

    if (maxVal > 0) {
      const angle = (maxHour / 24) * 360 - 90;
      const rad = (angle * Math.PI) / 180;
      const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      dot.setAttribute('cx', 100 + 70 * Math.cos(rad));
      dot.setAttribute('cy', 100 + 70 * Math.sin(rad));
      dot.setAttribute('r', '6');
      dot.setAttribute('fill', 'var(--accent)');
      svg.appendChild(dot);
    }

    document.getElementById('clock-visual').innerHTML = '';
    document.getElementById('clock-visual').appendChild(svg);
  },

  // ===== Library =====
  async loadLibrary() {
    try {
      const data = await this.fetchJSON('/api/library');

      document.getElementById('library-stats').innerHTML = `
        <div class="stat-card" style="flex:1;min-width:120px">
          <div class="stat-value">${data.saved_tracks.length}</div>
          <div class="stat-label">Saved Tracks</div>
        </div>
        <div class="stat-card" style="flex:1;min-width:120px">
          <div class="stat-value">${data.saved_albums.length}</div>
          <div class="stat-label">Saved Albums</div>
        </div>
        <div class="stat-card" style="flex:1;min-width:120px">
          <div class="stat-value">${data.playlists.length}</div>
          <div class="stat-label">Playlists</div>
        </div>
      `;

      document.getElementById('saved-tracks-count').textContent = `${data.saved_tracks.length}`;
      document.getElementById('saved-albums-count').textContent = `${data.saved_albums.length}`;
      document.getElementById('playlists-count').textContent = `${data.playlists.length}`;

      // Saved tracks table
      document.getElementById('saved-tracks-table').innerHTML = data.saved_tracks.slice(0, 30).map(t => `
        <div class="lib-item">
          <div class="lib-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
          </div>
          <div class="lib-info">
            <div class="lib-name">${this.esc(t.name)}</div>
            <div class="lib-artist">${this.esc(t.artist)}</div>
          </div>
          <div class="lib-meta">${t.duration_formatted}</div>
        </div>
      `).join('') || '<p class="empty-state">No saved tracks.</p>';

      // Saved albums table
      document.getElementById('saved-albums-table').innerHTML = data.saved_albums.slice(0, 20).map(a => `
        <div class="lib-item">
          <div class="lib-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
          </div>
          <div class="lib-info">
            <div class="lib-name">${this.esc(a.name)}</div>
            <div class="lib-artist">${this.esc(a.artist)}</div>
          </div>
          <div class="lib-meta">${a.release_date?.slice(0, 4) || '?'} · ${a.total_tracks || '?'} tracks</div>
        </div>
      `).join('') || '<p class="empty-state">No saved albums.</p>';

      // Playlists
      document.getElementById('playlists-table').innerHTML = data.playlists.map(p => `
        <div class="lib-item">
          <div class="lib-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </div>
          <div class="lib-info">
            <div class="lib-name">${this.esc(p.name)}</div>
            <div class="lib-artist">${p.description ? this.esc(p.description).slice(0, 50) : 'No description'}</div>
          </div>
          <div class="lib-meta">${p.tracks_total || 0} tracks</div>
        </div>
      `).join('') || '<p class="empty-state">No playlists.</p>';

    } catch (err) {
      console.error('Failed to load library:', err);
    }
  },

  // ===== Intelligence =====
  async loadIntelligence() {
    try {
      const analytics = await this.fetchJSON('/api/analytics');

      // Anomalies
      const anomalies = analytics.anomalies?.findings || [];
      document.getElementById('anomalies-count').textContent = `${anomalies.length} findings`;

      if (anomalies.length > 0) {
        document.getElementById('anomalies-grid').innerHTML = anomalies.slice(0, 8).map(a => `
          <div class="anomaly-card">
            <div class="anomaly-type">${a.type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</div>
            <div class="anomaly-text">${this.esc(a.description)}</div>
          </div>
        `).join('');
      } else {
        document.getElementById('anomalies-grid').innerHTML = '<p class="empty-state">No anomalies detected yet. As your listening history grows, interesting patterns will be discovered automatically.</p>';
      }

      // Recommendations
      const recs = analytics.recommendations?.recommendations || [];
      document.getElementById('recs-count').textContent = `${recs.length} suggestions`;

      if (recs.length > 0) {
        document.getElementById('recs-list').innerHTML = recs.map(r => `
          <div class="rec-card">
            <div class="rec-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            </div>
            <div class="rec-content">
              <div class="rec-name">${r.type === 'adjacent_artist' ? r.artist : r.track}${r.album ? ` (${r.album})` : ''}</div>
              <div class="rec-reason">${this.esc(r.reason)}</div>
            </div>
          </div>
        `).join('');
      } else {
        document.getElementById('recs-list').innerHTML = '<p class="empty-state">Not enough data yet for personalized recommendations. Your recommendations will appear here as your library grows.</p>';
      }

      // Generate AI insights from analytics
      this.generateInsights(analytics);

    } catch (err) {
      console.error('Failed to load intelligence:', err);
    }
  },

  generateInsights(analytics) {
    const insights = [];

    const tl = analytics.total_listening;
    if (tl.total_plays > 0) {
      insights.push({
        text: `You've accumulated <strong>${tl.total_plays.toLocaleString()} plays</strong> across <strong>${tl.unique_artists} artists</strong> and <strong>${tl.unique_tracks} tracks</strong>, spanning ${tl.date_range_days.toFixed(0)} days of listening history.`,
        source: 'Total listening metric'
      });
    }

    const gd = analytics.genre_diversity;
    if (gd.genre_count > 0) {
      insights.push({
        text: `Your listening spans <strong>${gd.genre_count} distinct genres</strong> across ${Object.keys(this.esc_counts(gd.top_genres)).length} genre families. Your top genre is <strong>${gd.top_genres[0]?.genre || 'N/A'}</strong>, accounting for ${gd.top_genres[0]?.share_pct || 0}% of your listening.`,
        source: 'Genre diversity analysis'
      });
    }

    const rr = analytics.repeat_rate;
    if (rr.repeat_rate_tracks > 0) {
      insights.push({
        text: `Your repeat rate is <strong>${rr.repeat_rate_tracks}%</strong> for tracks and <strong>${rr.repeat_rate_artists}%</strong> for artists. You have <strong>${rr.repeated_tracks_count} replayed tracks</strong> and <strong>${rr.repeated_artists_count} replayed artists</strong>.`,
        source: 'Repeat rate analysis'
      });
    }

    const dr = analytics.discovery_rate;
    if (dr.discovery_rate > 0) {
      insights.push({
        text: `You discover new music at a <strong>${dr.discovery_rate}%</strong> rate — ${dr.one_time_tracks} of your ${dr.total_unique_tracks} unique tracks were one-time listens. This suggests a <strong>${dr.discovery_score > 50 ? 'highly exploratory' : 'comfort-oriented'}</strong> listening style.`,
        source: 'Discovery vs comfort analysis'
      });
    }

    const al = analytics.album_loyalty;
    if (al.album_loyalty_score > 0) {
      insights.push({
        text: `Your album depth score is <strong>${al.album_loyalty_score}x</strong> on average — meaning you replay album tracks ${al.album_loyalty_score} times per unique track. ${al.deep_albums.length > 0 ? `Your deepest album is <strong>${al.deep_albums[0].album_name}</strong> at ${al.deep_albums[0].depth_score}x depth.` : ''}`,
        source: 'Album loyalty analysis'
      });
    }

    const arch = analytics.listener_archetype;
    insights.push({
      text: `Your listener archetype is <strong>${arch.archetype}</strong>, based on ${arch.archetype_signals.length} measurable signals from your listening data. ${arch.archetype_signals.map(s => s.description).join(' ')}`,
      source: 'Listener archetype analysis'
    });

    const dna = analytics.music_dna?.dna || {};
    const dnaEntries = Object.entries(dna).filter(([_, v]) => v.label && v.label !== 'Unknown');
    if (dnaEntries.length > 0) {
      const dnaText = dnaEntries.slice(0, 4).map(([k, v]) => `${v.label} (${k.replace(/_/g, ' ')})`).join(' · ');
      insights.push({
        text: `Your Music DNA reveals: <strong>${dnaText}</strong>`,
        source: 'Music DNA profile'
      });
    }

    // Audio characteristics
    const audio = analytics.audio_characteristics;
    if (audio.interpretation && Object.keys(audio.audio_characteristics).length > 0) {
      const audioText = Object.entries(audio.interpretation).slice(0, 3).map(([k, v]) => v).join('. ');
      insights.push({
        text: `Audio profile: ${audioText}`,
        source: 'Audio feature analysis'
      });
    }

    const insightsEl = document.getElementById('insights-list');
    if (insights.length > 0) {
      insightsEl.innerHTML = insights.map(i => `
        <div class="insight-card">
          <div class="insight-text">${i.text}</div>
          <div class="insight-source">Source: ${i.source}</div>
        </div>
      `).join('');
    } else {
      insightsEl.innerHTML = '<p class="empty-state">Insights will be generated from your listening data.</p>';
    }
  },

  esc_counts(obj) { return Object.keys(obj).length; },

  // ===== Live =====
  startLivePolling() {
    // Poll every 10 seconds
    this.currentlyPlayingInterval = setInterval(() => this.pollCurrentlyPlaying(), 10000);
    this.pollCurrentlyPlaying();
  },

  async pollCurrentlyPlaying() {
    try {
      const data = await this.fetchJSON('/api/currently-playing');
      const statusDot = document.getElementById('live-status-dot');
      const statusText = document.getElementById('live-status-text');
      const player = document.getElementById('live-player');

      if (data.playing && data.track) {
        statusDot.className = 'status-dot connected';
        statusText.textContent = 'Live';

        player.innerHTML = `
          <div class="live-track">
            <div class="live-track-artist">${this.esc(data.track.artist)}</div>
            <div class="live-track-name">${this.esc(data.track.name)}</div>
            <div class="live-track-album">${data.track.album ? this.esc(data.track.album) : 'Unknown album'}</div>
            ${data.audio_features ? this.renderAudioFeatures(data.audio_features) : ''}
            <div class="live-audio" style="margin-top:20px">
              <div class="live-audio-item">
                <div class="live-audio-label">Progress</div>
                <div class="live-audio-value">${this.formatTime(data.progress_ms || 0)}</div>
              </div>
              <div class="live-audio-item">
                <div class="live-audio-label">Status</div>
                <div class="live-audio-value" style="color:var(--accent)">${data.is_playing ? 'Playing' : 'Paused'}</div>
              </div>
            </div>
          </div>
        `;
      } else if (data.message) {
        statusDot.className = 'status-dot';
        statusText.textContent = 'Idle';
        player.innerHTML = `
          <div class="live-placeholder">
            <div class="pulse"></div>
            <p>${data.message}</p>
          </div>
        `;
      }
    } catch (err) {
      console.error('Live polling error:', err);
    }
  },

  renderAudioFeatures(af) {
    const items = [
      { label: 'Energy', value: (af.energy * 100).toFixed(0) + '%' },
      { label: 'Danceability', value: (af.danceability * 100).toFixed(0) + '%' },
      { label: 'Valence', value: (af.valence * 100).toFixed(0) + '%' },
      { label: 'Acoustic', value: (af.acousticness * 100).toFixed(0) + '%' },
    ].filter(i => i.value !== '0%');

    return `
      <div class="live-audio">
        ${items.map(i => `
          <div class="live-audio-item">
            <div class="live-audio-label">${i.label}</div>
            <div class="live-audio-value">${i.value}</div>
          </div>
        `).join('')}
      </div>
    `;
  },

  formatTime(ms) {
    const totalSec = Math.floor(ms / 1000);
    const min = Math.floor(totalSec / 60);
    const sec = totalSec % 60;
    return `${min}:${sec.toString().padStart(2, '0')}`;
  },

  esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },

  destroyChart(id) {
    if (this.charts[id]) {
      this.charts[id].destroy();
      delete this.charts[id];
    }
  },

  async fetchJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return res.json();
  },
};

document.addEventListener('DOMContentLoaded', () => App.init());
