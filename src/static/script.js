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
            
            // Enable preview button once loaded and selected
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

    // --- Reddit URL Fetch ---
    const btnFetchReddit = document.getElementById('btnFetchReddit');
    const redditUrlInput = document.getElementById('redditUrl');
    const fetchStatus = document.getElementById('fetchStatus');

    if (btnFetchReddit && redditUrlInput && fetchStatus) {
        btnFetchReddit.addEventListener('click', async () => {
            const url = redditUrlInput.value.trim();
            if (!url) {
                fetchStatus.textContent = '⚠️ Please paste a Reddit URL first.';
                fetchStatus.className = 'fetch-status fetch-error';
                return;
            }

            // Reset status and disable button
            fetchStatus.textContent = '';
            fetchStatus.className = 'fetch-status';
            btnFetchReddit.innerHTML = '<span class="icon">⌛</span> Fetching...';
            btnFetchReddit.disabled = true;

            try {
                const formData = new FormData();
                formData.append('url', url);

                const res = await fetch('/api/fetch-reddit-post', {
                    method: 'POST',
                    body: formData
                });

                if (!res.ok) {
                    const errData = await res.json();
                    throw new Error(errData.detail || `Server error (${res.status})`);
                }

                const data = await res.json();

                // Populate Story textarea
                if (storyText) storyText.value = data.body;

                // Populate Reddit Intro Card fields
                if (postTitle) postTitle.value = data.title;
                if (postSubreddit) postSubreddit.value = data.subreddit;
                if (postUsername) postUsername.value = data.author;
                if (postScore) postScore.value = data.score;

                // Trigger card preview update
                updateCardPreview();

                fetchStatus.textContent = `✅ Fetched: "${data.title.substring(0, 60)}${data.title.length > 60 ? '...' : ''}"`;
                fetchStatus.className = 'fetch-status fetch-success';
                btnFetchReddit.innerHTML = '<span class="icon">🔗</span> Fetch';

            } catch (err) {
                console.error('Fetch Reddit Error:', err);
                fetchStatus.textContent = `❌ ${err.message}`;
                fetchStatus.className = 'fetch-status fetch-error';
                btnFetchReddit.innerHTML = '<span class="icon">🔗</span> Fetch';
            } finally {
                btnFetchReddit.disabled = false;
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

    renderForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Prevent double submit
        if (btnRender.disabled) return;
        
        btnRender.disabled = true;
        btnRender.innerHTML = '<span class="icon">🚀</span> Launching Pipeline...';
        terminalLog.innerHTML = '';
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
                addLog("The pipeline is now running in the background.");
                
                btnRender.innerHTML = '<span class="icon">✅</span> Processing...';
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
});
