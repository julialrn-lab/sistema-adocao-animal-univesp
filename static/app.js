// Script web JavaScript: filtro acessível de animais disponíveis para adoção.
document.addEventListener('DOMContentLoaded', () => {
  const busca = document.querySelector('#busca');
  if (!busca) return;
  const cards = Array.from(document.querySelectorAll('.animal'));
  const vazio = document.querySelector('#sem-resultado');
  busca.addEventListener('input', () => {
    const termo = busca.value.trim().toLocaleLowerCase('pt-BR');
    let visiveis = 0;
    for (const card of cards) {
      const mostra = (card.dataset.nome || '').includes(termo);
      card.hidden = !mostra;
      if (mostra) visiveis++;
    }
    if (vazio) vazio.hidden = visiveis > 0 || cards.length === 0;
  });
});
