FROM node:20-slim

RUN apt-get update && apt-get install -y \
    curl \
    git \
    vim \
    htop \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -L https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 -o /usr/local/bin/ttyd \
    && chmod +x /usr/local/bin/ttyd

RUN npm install -g @anthropic-ai/claude-code

# Persistir sessão do Claude
ENV CLAUDE_CONFIG_DIR=/root/.claude

WORKDIR /workspace
EXPOSE 7681

CMD ["ttyd", "-W", "-t", "fontSize=14", "bash"]
