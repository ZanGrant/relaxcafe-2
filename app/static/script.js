function showToast(message, type) {
    type = type?.trim().toLowerCase(); 
    const container = document.getElementById('toast-container');

    // Batasi maksimal 5 notifikasi
    if (container.children.length >= 4) {
        container.removeChild(container.firstElementChild);
    }

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

function toggleButtonOverlay(id) {
    const overlay = document.getElementById(id);
    if (overlay) {
        overlay.classList.toggle('hidden');
    }
}

function addTanggalRangeValidator(formId, startId = 'start', endId = 'end') {
    const form = document.getElementById(formId);
    if (!form) return;

    form.addEventListener('submit', function(e) {
        const start = form.querySelector(`#${startId}`).value;
        const end = form.querySelector(`#${endId}`).value;

        if (start && end && start > end) {
            e.preventDefault();
            showToast('Tanggal akhir tidak boleh lebih awal dari tanggal mulai.', 'error');
        }
    });
}

