document.addEventListener('DOMContentLoaded', () => {
    // --- Elements ---
    const voiceSelect = document.getElementById('voiceSelect');
    const btnPreviewAudio = document.getElementById('btnPreviewAudio');
    const audioPlayer = document.getElementById('audioPlayer');
    const renderForm = document.getElementById('renderForm');
    const btnRender = document.getElementById('btnRender');
    
    // Style Elements
    const fontSizeSlider = document.getElementById('fontSize');
    const fontSizeDisplay = document.getElementById('fontSizeDisplay');
    const strokeWidthSlider = document.getElementById('strokeWidth');
    const strokeWidthDisplay = document.getElementById('strokeWidthDisplay');
    const fontColorPicker = document.getElementById('fontColor');
    const strokeColorPicker = document.getElementById('strokeColor');
    
    // Preview Elements
    const subtitleContainer = document.querySelector('.subtitle-container');
    const previewHighlight = document.getElementById('previewHighlight');
    
    // Terminal
    const terminalLog = document.getElementById('terminalLog');

    // --- State & Initialization ---
    
    // Fetch Voices
    async function loadVoices() {
        try {
            const res = await fetch('/api/voices');
            const data = await res.json();
            
            voiceSelect.innerHTML = '<option value="" disabled selected>Select a voice...</option>';
            data.voices.forEach(voice => {
                const opt = document.createElement('option');
                opt.value = voice.id;
                opt.textContent = voice.display;
                voiceSelect.appendChild(opt);
            });

            // Restore last-used voice so repeat visits are one-click
            const lastVoice = localStorage.getItem('reelmaker.lastVoice');
            if (lastVoice && Array.from(voiceSelect.options).some(o => o.value === lastVoice)) {
                voiceSelect.value = lastVoice;
                btnPreviewAudio.disabled = false;
            }

            voiceSelect.addEventListener('change', () => {
                btnPreviewAudio.disabled = !voiceSelect.value;
            });

        } catch (err) {
            console.error(err);
            voiceSelect.innerHTML = '<option value="" disabled>Failed to load voices</option>';
        }
    }
    
    loadVoices();

    // Fetch Assets (Videos & Music)
    async function loadAssets() {
        try {
            const res = await fetch('/api/assets');
            const data = await res.json();
            
            const bgVideoSelect = document.getElementById('bgVideo');
            const bgMusicSelect = document.getElementById('bgMusic');
            
            if (bgVideoSelect) {
                // Clear everything except the first option (Random)
                while (bgVideoSelect.options.length > 1) bgVideoSelect.remove(1);

                data.videos.forEach(vid => {
                    const opt = document.createElement('option');
                    opt.value = vid;
                    opt.textContent = vid;
                    bgVideoSelect.appendChild(opt);
                });
            }
            
            if (bgMusicSelect) {
                // Clear everything except Random and None (first two)
                while (bgMusicSelect.options.length > 2) bgMusicSelect.remove(2);

                data.music.forEach(mus => {
                    const opt = document.createElement('option');
                    opt.value = mus;
                    opt.textContent = mus;
                    bgMusicSelect.appendChild(opt);
                });
            }
            addLog(`Assets loaded: ${data.videos.length} videos, ${data.music.length} tracks.`);
        } catch (err) {
            console.error("Failed to load assets:", err);
            addLog("❌ Failed to load videos/music list.");
        }
    }
    loadAssets();

    // --- Audio Preview ---
    
    btnPreviewAudio.addEventListener('click', async () => {
        if (!voiceSelect.value) return;
        
        btnPreviewAudio.innerHTML = '<span class="icon">⌛</span> Loading...';
        btnPreviewAudio.disabled = true;
        
        try {
            // Point directly to the statically generated demo file
            const audioUrl = `/static/demos/${voiceSelect.value}.mp3`;
            
            audioPlayer.src = audioUrl;
            await audioPlayer.play();
            
            btnPreviewAudio.innerHTML = '<span class="icon">🔊</span> Playing';
            
            audioPlayer.onended = () => {
                btnPreviewAudio.innerHTML = '<span class="icon">▶️</span> Demo';
                btnPreviewAudio.disabled = false;
            };
            
        } catch (err) {
            console.error(err);
            btnPreviewAudio.innerHTML = '<span class="icon">❌</span> Error';
            setTimeout(() => {
                btnPreviewAudio.innerHTML = '<span class="icon">▶️</span> Demo';
                btnPreviewAudio.disabled = false;
            }, 2000);
        }
    });

    // --- Live Subtitle Styling ---
    
    function updatePreview() {
        const size = fontSizeSlider.value;
        const sw = strokeWidthSlider.value;
        const color = fontColorPicker.value;
        const strokeColor = strokeColorPicker.value;
        
        // Update display text
        fontSizeDisplay.textContent = size;
        strokeWidthDisplay.textContent = sw;
        
        // Update CSS variables for live preview Box
        subtitleContainer.style.setProperty('--p-size', `${size}px`);
        subtitleContainer.style.setProperty('--p-color', color);
        subtitleContainer.style.setProperty('--p-stroke', strokeColor);
        subtitleContainer.style.setProperty('--p-sw', `${sw}px`);
    }

    fontSizeSlider.addEventListener('input', updatePreview);
    strokeWidthSlider.addEventListener('input', updatePreview);
    fontColorPicker.addEventListener('input', updatePreview);
    strokeColorPicker.addEventListener('input', updatePreview);


    // Initial setup
    updatePreview();

    // --- Video Settings Sliders ---
    const videoSpeedSlider = document.getElementById('videoSpeed');
    const videoSpeedDisplay = document.getElementById('videoSpeedDisplay');
    if (videoSpeedSlider && videoSpeedDisplay) {
        videoSpeedSlider.addEventListener('input', (e) => {
            let val = parseFloat(e.target.value).toFixed(1);
            videoSpeedDisplay.textContent = `${val}x`;
        });
    }

    const ttsRateSlider = document.getElementById('ttsRate');
    const ttsRateDisplay = document.getElementById('ttsRateDisplay');
    if (ttsRateSlider && ttsRateDisplay) {
        ttsRateSlider.addEventListener('input', (e) => {
            let val = parseInt(e.target.value);
            let sign = val >= 0 ? '+' : '';
            ttsRateDisplay.textContent = `${sign}${val}`;
        });
    }

    const maxDurationSlider = document.getElementById('maxDuration');
    const maxDurationDisplay = document.getElementById('maxDurationDisplay');
    if (maxDurationSlider && maxDurationDisplay) {
        maxDurationSlider.addEventListener('input', (e) => {
             maxDurationDisplay.textContent = e.target.value;
        });
    }


    // --- Reddit Card Live Preview ---
    const postTitle    = document.getElementById('postTitle');
    const postSubreddit = document.getElementById('postSubreddit');
    const postUsername = document.getElementById('postUsername');
    const postScore    = document.getElementById('postScore');
    const postComments = document.getElementById('postComments');
    const postAge      = document.getElementById('postAge');
    const mockTitle    = document.getElementById('mockTitle');
    const mockSubreddit = document.getElementById('mockSubreddit');
    const mockMeta     = document.getElementById('mockMeta');
    const mockScore    = document.getElementById('mockScore');
    const mockComments = document.getElementById('mockComments');

    function fmtNum(n) {
        n = parseInt(n) || 0;
        if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
        return n ? String(n) : '–';
    }

    function updateCardPreview() {
        if (mockTitle)    mockTitle.textContent    = postTitle?.value.trim()    || 'Your post title will appear here';
        if (mockSubreddit) mockSubreddit.textContent = 'r/' + (postSubreddit?.value.trim().replace(/^r\/?/, '') || 'AskReddit');
        if (mockMeta)     mockMeta.textContent     = (postUsername?.value.trim() || 'u/user') + ' · ' + (postAge?.value.trim() || '2d');
        if (mockScore)    mockScore.textContent    = fmtNum(postScore?.value);
        if (mockComments) mockComments.textContent = fmtNum(postComments?.value);
    }

    [postTitle, postSubreddit, postUsername, postScore, postComments, postAge].forEach(el => {
        el?.addEventListener('input', updateCardPreview);
    });
    updateCardPreview();

    // --- OCR Screenshot Upload ---
    const btnOcr = document.getElementById('btnOcr');
    const ocrFileInput = document.getElementById('ocrFileInput');
    const ocrStatus = document.getElementById('ocrStatus');

    if (btnOcr && ocrFileInput && ocrStatus) {
        btnOcr.addEventListener('click', () => ocrFileInput.click());

        ocrFileInput.addEventListener('change', async () => {
            const file = ocrFileInput.files[0];
            if (!file) return;

            ocrStatus.textContent = '';
            ocrStatus.className = 'fetch-status';
            btnOcr.innerHTML = '<span class="icon">⌛</span> Extracting text...';
            btnOcr.disabled = true;

            try {
                const formData = new FormData();
                formData.append('image', file);

                const res = await fetch('/api/process_ocr', {
                    method: 'POST',
                    body: formData
                });

                if (!res.ok) {
                    const errData = await res.json();
                    throw new Error(errData.detail || `Server error (${res.status})`);
                }

                const data = await res.json();
                if (storyText) storyText.value = data.text;

                ocrStatus.textContent = `✅ Extracted ${data.text.length} characters from screenshot.`;
                ocrStatus.className = 'fetch-status fetch-success';
                btnOcr.innerHTML = '<span class="icon">📷</span> Upload Another Screenshot';

            } catch (err) {
                console.error('OCR Error:', err);
                ocrStatus.textContent = `❌ ${err.message}`;
                ocrStatus.className = 'fetch-status fetch-error';
                btnOcr.innerHTML = '<span class="icon">📷</span> Upload Screenshot & Extract Text';
            } finally {
                btnOcr.disabled = false;
                ocrFileInput.value = ''; // Reset so same file can be re-selected
            }
        });
    }

    // --- Form Submission & Rendering ---
    
    function addLog(msg) {
        const div = document.createElement('div');
        div.className = 'log-line';
        div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
        terminalLog.appendChild(div);
        terminalLog.scrollTop = terminalLog.scrollHeight;
    }

    function addRawLogs(rawText) {
        rawText
            .split(/\r?\n/)
            .map(line => line.trimEnd())
            .filter(Boolean)
            .forEach(line => addLog(line));
    }

    function setRenderButton(label, disabled) {
        btnRender.innerHTML = label;
        btnRender.disabled = disabled;
    }

    async function monitorPipeline(jobId) {
        let offset = 0;

        while (true) {
            const res = await fetch(`/api/process_status?job_id=${encodeURIComponent(jobId)}&offset=${offset}`);
            if (!res.ok) {
                throw new Error(`Status polling failed (${res.status})`);
            }

            const data = await res.json();
            offset = data.offset ?? offset;

            if (data.logs) {
                addRawLogs(data.logs);
            }

            if (data.state === 'completed') {
                addLog('Pipeline finished successfully.');
                setRenderButton('<span class="icon">🚀</span> Generate Reel', false);
                if (typeof loadOutputVideos === 'function') loadOutputVideos();
                return;
            }

            if (data.state === 'failed') {
                addLog(`Pipeline failed: ${data.error || 'Unknown error'}`);
                setRenderButton('<span class="icon">⚠️</span> Failed. Try Again.', false);
                return;
            }

            await new Promise(resolve => setTimeout(resolve, 1500));
        }
    }

    renderForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Prevent double submit
        if (btnRender.disabled) return;
        
        btnRender.disabled = true;
        btnRender.innerHTML = '<span class="icon">🚀</span> Launching Pipeline...';
        terminalLog.innerHTML = '';
        // Scroll terminal into view so user can see the log output
        terminalLog.scrollIntoView({ behavior: 'smooth', block: 'start' });
        addLog("Initializing rendering pipeline...");
        
        const formData = new FormData(renderForm);
        
        // Format tts_rate value correctly for back-end (e.g. "+15%")
        const rateVal = parseInt(ttsRateSlider.value);
        const signedRate = (rateVal >= 0 ? '+' : '') + rateVal + '%';
        formData.set('tts_rate', signedRate);
        
        try {
            addLog(`Submitting request to /api/process...`);
            const res = await fetch('/api/process', {
                method: 'POST',
                body: formData
            });
            
            if (res.ok) {
                const data = await res.json();
                addLog(`✅ Server: ${data.status}`);
                addLog("Connected to live pipeline logs.");

                btnRender.innerHTML = '<span class="icon">✅</span> Processing...';

                // Remember the voice so next visit skips the pick.
                if (voiceSelect.value) {
                    localStorage.setItem('reelmaker.lastVoice', voiceSelect.value);
                }

                await monitorPipeline(data.job_id);
            } else {
                const errText = await res.text();
                addLog(`❌ Server Error: ${res.status} - ${errText}`);
                throw new Error(errText || "Server rejected job.");
            }
        } catch (err) {
            console.error(err);
            addLog(`Error: ${err.message}`);
            btnRender.disabled = false;
            btnRender.innerHTML = '<span class="icon">⚠️</span> Failed. Try Again.';
        }
    });

    // --- AI Caption Generation ---
    const btnGenerateCaption = document.getElementById('btnGenerateCaption');
    const aiCaptionOutput = document.getElementById('aiCaptionOutput');
    const storyText = document.getElementById('storyText');

    if (btnGenerateCaption && aiCaptionOutput && storyText) {
        btnGenerateCaption.addEventListener('click', async () => {
            const textValue = storyText.value.trim();
            if (!textValue) {
                alert("Please paste your Script/Story on the left first!");
                return;
            }

            btnGenerateCaption.innerHTML = '<span class="icon">⌛</span> Thinking...';
            btnGenerateCaption.disabled = true;

            try {
                const formData = new FormData();
                formData.append('text', textValue);

                const res = await fetch('/api/generate_caption', {
                    method: 'POST',
                    body: formData
                });

                if (!res.ok) {
                    const errResponse = await res.json();
                    throw new Error(errResponse.detail || "API failed");
                }

                const data = await res.json();
                aiCaptionOutput.value = data.caption;
                btnGenerateCaption.innerHTML = '<span class="icon">✨</span> Generate Another';

            } catch (err) {
                console.error(err);
                aiCaptionOutput.value = `Error: ${err.message}`;
                btnGenerateCaption.innerHTML = '<span class="icon">❌</span> Failed';
                setTimeout(() => {
                    btnGenerateCaption.innerHTML = '<span class="icon">✨</span> Try Again';
                }, 3000);
            } finally {
                btnGenerateCaption.disabled = false;
            }
        });
    }

    // --- Thumbnail Generation ---
    const btnGenerateThumbnail = document.getElementById('btnGenerateThumbnail');
    const thumbnailText = document.getElementById('thumbnailText');
    const thumbnailResultBox = document.getElementById('thumbnailResultBox');
    const thumbnailPreview = document.getElementById('thumbnailPreview');
    const btnDownloadThumbnail = document.getElementById('btnDownloadThumbnail');

    if (btnGenerateThumbnail && thumbnailText) {
        btnGenerateThumbnail.addEventListener('click', async () => {
            const textVal = thumbnailText.value.trim();
            if (!textVal) {
                alert("Please enter some text for the thumbnail first!");
                return;
            }

            btnGenerateThumbnail.innerHTML = '<span class="icon">⌛</span> Rendering...';
            btnGenerateThumbnail.disabled = true;

            try {
                const formData = new FormData();
                formData.append('thumbnail_text', textVal);
                // Also pass current styling so they match the reel!
                formData.append('font_color', fontColorPicker.value);
                formData.append('stroke_color', strokeColorPicker.value);
                formData.append('stroke_width', strokeWidthSlider.value);

                const res = await fetch('/api/generate_thumbnail', {
                    method: 'POST',
                    body: formData
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || "Thumbnail generation failed");
                }

                const data = await res.json();
                
                // Show the image
                // To avoid caching issues with same filename, add a timestamp
                thumbnailPreview.src = `${data.thumbnail_url}?t=${new Date().getTime()}`;
                btnDownloadThumbnail.href = data.thumbnail_url;
                thumbnailResultBox.style.display = 'block';

                btnGenerateThumbnail.innerHTML = '<span class="icon">🖼️</span> Generate New';

            } catch (err) {
                console.error(err);
                alert(`Error: ${err.message}`);
                btnGenerateThumbnail.innerHTML = '<span class="icon">❌</span> Failed';
                setTimeout(() => {
                    btnGenerateThumbnail.innerHTML = '<span class="icon">🖼️</span> Generate Thumbnail';
                }, 2000);
            } finally {
                btnGenerateThumbnail.disabled = false;
            }
        });
    }
    // --- Paste from Reddit ---
    const smartPasteInput = document.getElementById('smartPasteInput');
    const btnSmartParse = document.getElementById('btnSmartParse');
    const btnClearForm = document.getElementById('btnClearForm');
    const smartPasteStatus = document.getElementById('smartPasteStatus');

    // Parses a block copy-pasted directly from reddit.com. Example shape:
    //   Go to AITAH
    //   r/AITAH
    //   •
    //   9m ago
    //   Username
    //
    //   Post title
    //   Body paragraphs...
    //
    //   Upvote
    //   1200
    //   Downvote
    //   45
    //   Go to comments
    //   Share
    function parseRedditPaste(raw) {
        const text = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        const lines = text.split('\n').map(s => s.trim());

        let subredditIdx = -1, subreddit = '';
        for (let i = 0; i < lines.length; i++) {
            const m = lines[i].match(/^r\/([A-Za-z0-9_]+)$/);
            if (m) { subreddit = m[1]; subredditIdx = i; break; }
        }
        if (!subreddit) return { error: "Couldn't find an 'r/subreddit' line — is this really a Reddit paste?" };

        let ageIdx = -1, age = '';
        const ageRe = /^(\d+\s*(?:s|sec|secs|m|min|mins|h|hr|hrs|d|day|days|w|wk|wks|mo|y|yr|yrs))\s+ago$/i;
        for (let i = subredditIdx + 1; i < lines.length; i++) {
            const m = lines[i].match(ageRe);
            if (m) { age = m[1].replace(/\s+/g, ''); ageIdx = i; break; }
        }
        if (!age) return { error: "Couldn't find a post age like '9m ago'." };

        let userIdx = -1, username = '';
        for (let i = ageIdx + 1; i < lines.length; i++) {
            if (lines[i]) {
                username = 'u/' + lines[i].replace(/^u\//, '');
                userIdx = i;
                break;
            }
        }
        if (!username || username === 'u/') return { error: "Couldn't find a username after the age line." };

        let upvoteIdx = -1;
        for (let i = userIdx + 1; i < lines.length; i++) {
            if (lines[i] === 'Upvote') { upvoteIdx = i; break; }
        }
        if (upvoteIdx < 0) return { error: "Couldn't find the 'Upvote' marker that ends the body." };

        let bodySlice = lines.slice(userIdx + 1, upvoteIdx);
        while (bodySlice.length && !bodySlice[0]) bodySlice.shift();
        while (bodySlice.length && !bodySlice[bodySlice.length - 1]) bodySlice.pop();
        if (!bodySlice.length) return { error: "Post body is empty." };

        const title = bodySlice[0];
        let bodyLines = bodySlice.slice(1);
        while (bodyLines.length && !bodyLines[0]) bodyLines.shift();
        const body = bodyLines.join('\n').replace(/\n{3,}/g, '\n\n').trim();

        function parseRedditNum(s) {
            const m = s.match(/^([\d.,]+)\s*([kmKM])?$/);
            if (!m) return null;
            const n = parseFloat(m[1].replace(/,/g, ''));
            if (isNaN(n)) return null;
            const suf = (m[2] || '').toLowerCase();
            if (suf === 'k') return Math.round(n * 1000);
            if (suf === 'm') return Math.round(n * 1_000_000);
            return Math.round(n);
        }

        const stopMarkers = new Set(['Downvote', 'Go to comments', 'Share']);

        let score = 0, scoreIdx = upvoteIdx;
        for (let i = upvoteIdx + 1; i < lines.length; i++) {
            if (!lines[i]) continue;
            if (stopMarkers.has(lines[i])) break;
            const v = parseRedditNum(lines[i]);
            if (v !== null) { score = v; scoreIdx = i; break; }
        }

        let downvoteIdx = -1;
        for (let i = scoreIdx + 1; i < lines.length; i++) {
            if (lines[i] === 'Downvote') { downvoteIdx = i; break; }
            if (lines[i] === 'Go to comments' || lines[i] === 'Share') break;
        }
        const commentsStart = downvoteIdx >= 0 ? downvoteIdx + 1 : scoreIdx + 1;
        let comments = 0;
        for (let i = commentsStart; i < lines.length; i++) {
            if (!lines[i]) continue;
            if (lines[i] === 'Go to comments' || lines[i] === 'Share') break;
            const v = parseRedditNum(lines[i]);
            if (v !== null) { comments = v; break; }
        }

        return { subreddit, age, username, title, body, score, comments };
    }

    if (btnSmartParse && smartPasteInput) {
        btnSmartParse.addEventListener('click', () => {
            const raw = smartPasteInput.value.trim();
            if (!raw) {
                smartPasteStatus.textContent = '⚠️ Paste a Reddit post first.';
                smartPasteStatus.className = 'fetch-status fetch-error';
                return;
            }

            const data = parseRedditPaste(raw);
            if (data.error) {
                smartPasteStatus.textContent = `⚠️ ${data.error}`;
                smartPasteStatus.className = 'fetch-status fetch-error';
                return;
            }

            if (postSubreddit) postSubreddit.value = data.subreddit;
            if (postAge)       postAge.value = data.age;
            if (postUsername)  postUsername.value = data.username;
            if (postTitle)     postTitle.value = data.title;
            if (storyText)     storyText.value = data.body;
            if (postScore)     postScore.value = data.score;
            if (postComments)  postComments.value = data.comments;

            updateCardPreview();

            const short = data.title.length > 60 ? data.title.substring(0, 60) + '…' : data.title;
            smartPasteStatus.textContent = `✅ Parsed r/${data.subreddit} — "${short}"`;
            smartPasteStatus.className = 'fetch-status fetch-success';
            btnSmartParse.innerHTML = '<span class="icon">✅</span> Ready — hit Generate!';
            setTimeout(() => {
                btnSmartParse.innerHTML = '<span class="icon">🧠</span> Parse & Fill Fields';
            }, 2500);

            // One-click flow: jump the user straight to Generate.
            if (btnRender) {
                btnRender.scrollIntoView({ behavior: 'smooth', block: 'center' });
                setTimeout(() => btnRender.focus(), 500);
            }
        });
    }

    // Clear all form fields
    if (btnClearForm) {
        btnClearForm.addEventListener('click', () => {
            if (smartPasteInput) smartPasteInput.value = '';
            if (storyText) storyText.value = '';
            if (postTitle) postTitle.value = '';
            if (postSubreddit) postSubreddit.value = 'AskReddit';
            if (postUsername) postUsername.value = 'u/user';
            if (postScore) postScore.value = '0';
            if (postComments) postComments.value = '0';
            if (postAge) postAge.value = '2d';
            if (smartPasteStatus) { smartPasteStatus.textContent = ''; smartPasteStatus.className = 'fetch-status'; }
            updateCardPreview();
        });
    }

    // --- Instagram Upload ---
    const igVideoSelect = document.getElementById('igVideoSelect');
    const btnRefreshVideos = document.getElementById('btnRefreshVideos');
    const igCaption = document.getElementById('igCaption');
    const igAutoCaption = document.getElementById('igAutoCaption');
    const btnUploadInstagram = document.getElementById('btnUploadInstagram');
    const igUploadStatus = document.getElementById('igUploadStatus');

    async function loadOutputVideos() {
        if (!igVideoSelect) return;
        try {
            const res = await fetch('/api/list_output_videos');
            const data = await res.json();

            igVideoSelect.innerHTML = '';
            if (data.videos.length === 0) {
                igVideoSelect.innerHTML = '<option value="" disabled selected>No videos found — render one first!</option>';
                return;
            }

            data.videos.forEach((vid, i) => {
                const opt = document.createElement('option');
                opt.value = vid.name;
                opt.textContent = `${vid.name} (${vid.size_mb} MB)`;
                if (i === 0) opt.selected = true;
                igVideoSelect.appendChild(opt);
            });
        } catch (err) {
            console.error('Failed to load output videos:', err);
            igVideoSelect.innerHTML = '<option value="" disabled>Failed to load videos</option>';
        }
    }

    loadOutputVideos();

    if (btnRefreshVideos) {
        btnRefreshVideos.addEventListener('click', () => {
            loadOutputVideos();
        });
    }

    // Toggle caption textarea based on auto-caption checkbox
    if (igAutoCaption && igCaption) {
        igAutoCaption.addEventListener('change', () => {
            if (igAutoCaption.checked) {
                igCaption.placeholder = 'Caption will be auto-generated on upload...';
                igCaption.value = '';
            } else {
                igCaption.placeholder = 'Type your instagram caption here...';
            }
        });
    }

    if (btnUploadInstagram) {
        btnUploadInstagram.addEventListener('click', async () => {
            const selectedVideo = igVideoSelect?.value;
            if (!selectedVideo) {
                igUploadStatus.textContent = '⚠️ Please select a video first.';
                igUploadStatus.className = 'fetch-status fetch-error';
                return;
            }

            btnUploadInstagram.disabled = true;
            btnUploadInstagram.innerHTML = '<span class="icon">⌛</span> Logging in & Uploading...';
            igUploadStatus.textContent = '';
            igUploadStatus.className = 'fetch-status';

            try {
                const formData = new FormData();
                formData.append('video_filename', selectedVideo);
                formData.append('caption', igCaption?.value?.trim() || '');
                formData.append('auto_caption', igAutoCaption?.checked ? 'true' : 'false');

                const res = await fetch('/api/upload_instagram', {
                    method: 'POST',
                    body: formData
                });

                if (!res.ok) {
                    const errData = await res.json();
                    throw new Error(errData.detail || `Server error (${res.status})`);
                }

                const data = await res.json();
                igUploadStatus.textContent = `✅ Uploaded! Caption: "${data.caption_used?.substring(0, 60)}..."`;
                igUploadStatus.className = 'fetch-status fetch-success';
                btnUploadInstagram.innerHTML = '<span class="icon">✅</span> Uploaded!';

                setTimeout(() => {
                    btnUploadInstagram.innerHTML = '<span class="icon">📤</span> Upload Another';
                    btnUploadInstagram.disabled = false;
                }, 3000);

            } catch (err) {
                console.error('Instagram Upload Error:', err);
                igUploadStatus.textContent = `❌ ${err.message}`;
                igUploadStatus.className = 'fetch-status fetch-error';
                btnUploadInstagram.innerHTML = '<span class="icon">❌</span> Failed';

                setTimeout(() => {
                    btnUploadInstagram.innerHTML = '<span class="icon">📤</span> Upload to Instagram';
                    btnUploadInstagram.disabled = false;
                }, 3000);
            }
        });
    }
});
