FROM nginx:1.27-alpine

# Configuração: arquivos estáticos + proxy reverso /api -> backend + limites
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY site/ /usr/share/nginx/html/

EXPOSE 80
