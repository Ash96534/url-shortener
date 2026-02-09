from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl
from database import get_db, URL, Base, engine
import string
import os

app = FastAPI(title="URL Shortener v1.0", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

BASE62 = string.digits + string.ascii_lowercase + string.ascii_uppercase

def encode_base62(num: int) -> str:
    if num == 0:
        return BASE62[0]
    arr = []
    while num:
        num, rem = divmod(num, 62)
        arr.append(BASE62[rem])
    return ''.join(reversed(arr))

class URLCreate(BaseModel):
    url: HttpUrl

class URLResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: str

@app.post("/shorten", response_model=URLResponse)
def create_short_url(url_data: URLCreate, request: Request, db: Session = Depends(get_db)):
    db_url = URL(original_url=str(url_data.url))
    db.add(db_url)
    db.commit()
    db.refresh(db_url)
    
    short_code = encode_base62(db_url.id)
    db_url.short_code = short_code
    db.commit()
    
    base_url = str(request.base_url).rstrip('/')
    short_url = f"{base_url}/{short_code}"
    
    return {
        "short_code": short_code,
        "short_url": short_url,
        "original_url": db_url.original_url
    }

@app.get("/{short_code}")
def redirect_to_url(short_code: str, db: Session = Depends(get_db)):
    db_url = db.query(URL).filter(URL.short_code == short_code).first()
    if not db_url:
        raise HTTPException(status_code=404, detail="URL not found")
    
    db_url.clicks += 1
    db.commit()
    
    return RedirectResponse(url=db_url.original_url, status_code=307)

@app.get("/stats/{short_code}")
def get_stats(short_code: str, db: Session = Depends(get_db)):
    db_url = db.query(URL).filter(URL.short_code == short_code).first()
    if not db_url:
        raise HTTPException(status_code=404, detail="URL not found")
    
    return {
        "short_code": short_code,
        "original_url": db_url.original_url,
        "clicks": db_url.clicks,
        "created_at": db_url.created_at.isoformat()
    }

@app.get("/", response_class=HTMLResponse)
def read_root():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>URL Shortener v1.0</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .container {
                background: white;
                padding: 3rem;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                width: 90%;
                max-width: 500px;
            }
            h1 { 
                color: #333; 
                margin-bottom: 0.5rem;
                font-size: 2rem;
            }
            .version {
                color: #667eea;
                font-size: 0.9rem;
                margin-bottom: 2rem;
            }
            input {
                width: 100%;
                padding: 1rem;
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                font-size: 1rem;
                margin-bottom: 1rem;
                transition: border-color 0.3s;
            }
            input:focus {
                outline: none;
                border-color: #667eea;
            }
            button {
                width: 100%;
                padding: 1rem;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 1rem;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
            }
            button:disabled {
                opacity: 0.6;
                cursor: not-allowed;
                transform: none;
            }
            #result {
                margin-top: 1.5rem;
                padding: 1rem;
                background: #f8f9fa;
                border-radius: 10px;
                display: none;
            }
            #result.show { display: block; }
            .short-url {
                color: #667eea;
                font-weight: bold;
                word-break: break-all;
            }
            .error {
                color: #e74c3c;
                margin-top: 1rem;
            }
            .stats {
                margin-top: 0.5rem;
                font-size: 0.9rem;
                color: #666;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔗 URL Shortener</h1>
            <div class="version">Version 1.0.0</div>
            <input type="url" id="urlInput" placeholder="Paste your long URL here..." required>
            <button onclick="shortenUrl()" id="btn">Shorten URL</button>
            <div id="result"></div>
        </div>

        <script>
            async function shortenUrl() {
                const input = document.getElementById('urlInput');
                const btn = document.getElementById('btn');
                const result = document.getElementById('result');
                const url = input.value.trim();
                
                if (!url) {
                    showError('Please enter a URL');
                    return;
                }

                btn.disabled = true;
                btn.textContent = 'Shortening...';
                result.className = '';
                result.innerHTML = '';

                try {
                    const response = await fetch('/shorten', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: url })
                    });

                    const data = await response.json();
                    
                    if (!response.ok) {
                        throw new Error(data.detail || 'Failed to shorten URL');
                    }

                    result.innerHTML = `
                        <div>✅ Shortened successfully!</div>
                        <div class="short-url">
                            <a href="${data.short_url}" target="_blank">${data.short_url}</a>
                        </div>
                        <div class="stats">
                            Original: ${data.original_url.substring(0, 50)}${data.original_url.length > 50 ? '...' : ''}
                        </div>
                    `;
                    result.className = 'show';
                    input.value = '';
                } catch (err) {
                    showError(err.message);
                } finally {
                    btn.disabled = false;
                    btn.textContent = 'Shorten URL';
                }
            }

            function showError(msg) {
                const result = document.getElementById('result');
                result.innerHTML = `<div class="error">❌ ${msg}</div>`;
                result.className = 'show';
            }

            document.getElementById('urlInput').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') shortenUrl();
            });
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)