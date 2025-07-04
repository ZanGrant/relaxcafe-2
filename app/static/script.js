function showToast(message, type) {
    type = type?.trim().toLowerCase(); 
    const container = document.getElementById('toast-container');

    const toast = document.createElement('div');
    toast.className = `custom-alert show ${type === 'error' ? 'btn-red' : 'btn-green'}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            container.removeChild(toast);
        }, 300);
    }, 1500);

    console.log("Toast class:", toast.className);

}
