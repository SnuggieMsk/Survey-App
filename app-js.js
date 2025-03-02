// Main application JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Enable tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    if (tooltipTriggerList.length > 0) {
        const tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
    
    // Enable popovers
    const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
    if (popoverTriggerList.length > 0) {
        const popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
            return new bootstrap.Popover(popoverTriggerEl);
        });
    }
    
    // Flash message auto-close
    const flashMessages = document.querySelectorAll('.alert-dismissible');
    flashMessages.forEach(function(message) {
        setTimeout(function() {
            const dismissButton = message.querySelector('.btn-close');
            if (dismissButton) {
                dismissButton.click();
            }
        }, 5000);
    });
    
    // File input preview (for image uploads)
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', function(e) {
            const previewId = this.dataset.preview;
            if (previewId && this.files && this.files[0]) {
                const previewElement = document.getElementById(previewId);
                if (previewElement) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        previewElement.src = e.target.result;
                        previewElement.parentElement.classList.remove('d-none');
                    };
                    reader.readAsDataURL(this.files[0]);
                }
            }
        });
    });
    
    // Make question cards sortable if SortableJS is available
    if (typeof Sortable !== 'undefined' && document.getElementById('question-container')) {
        new Sortable(document.getElementById('question-container'), {
            animation: 150,
            handle: '.fa-grip-lines',
            ghostClass: 'sortable-ghost',
            onEnd: function(evt) {
                // Update question numbers after sorting
                const questionCards = document.querySelectorAll('.question-card');
                questionCards.forEach((card, index) => {
                    card.querySelector('h5').textContent = `Question ${index + 1}`;
                });
                
                // TODO: Add AJAX call to update positions in the database
            }
        });
    }
    
    // Make options sortable if SortableJS is available
    if (typeof Sortable !== 'undefined') {
        document.querySelectorAll('.options-container').forEach(function(container) {
            new Sortable(container, {
                animation: 150,
                ghostClass: 'sortable-ghost',
                onEnd: function(evt) {
                    // TODO: Add AJAX call to update positions in the database
                }
            });
        });
    }
    
    // Image choice options
    document.querySelectorAll('.image-choice-option').forEach(option => {
        option.addEventListener('click', function() {
            const container = this.closest('.image-choice-options');
            const radioInput = this.querySelector('input[type="radio"]');
            
            // Deselect all options
            container.querySelectorAll('.image-choice-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            
            // Select this option
            this.classList.add('selected');
            radioInput.checked = true;
        });
    });
    
    // Rating stars
    document.querySelectorAll('.stars .star').forEach(star => {
        star.addEventListener('click', function() {
            const stars = this.parentElement.querySelectorAll('.star');
            const value = parseInt(this.dataset.value);
            const hiddenInput = this.closest('.rating-container')?.querySelector('input[type="hidden"]');
            const valueDisplay = this.closest('.rating-container')?.querySelector('.rating-value');
            
            // Update stars
            stars.forEach((s, index) => {
                if (index < value) {
                    s.classList.add('active');
                } else {
                    s.classList.remove('active');
                }
            });
            
            // Update hidden input and display if they exist
            if (hiddenInput) hiddenInput.value = value;
            if (valueDisplay) valueDisplay.textContent = `${value} out of 5`;
        });
    });
    
    // Range sliders
    document.querySelectorAll('.custom-range').forEach(slider => {
        slider.addEventListener('input', function() {
            const value = this.value;
            const valueDisplay = this.closest('.slider-container')?.querySelector('.range-value') || 
                                this.closest('.slider-preview')?.querySelector('.range-value');
            
            if (valueDisplay) {
                valueDisplay.textContent = value;
            }
        });
    });
    
    // Copy link buttons
    const copyButtons = document.querySelectorAll('[id^="copy-"]');
    copyButtons.forEach(button => {
        button.addEventListener('click', function() {
            const inputId = this.dataset.input || this.id.replace('copy-', '');
            const inputElement = document.getElementById(inputId);
            
            if (inputElement) {
                inputElement.select();
                document.execCommand('copy');
                showToast('Link copied to clipboard!', 'success');
            }
        });
    });
});

// Toast notification helper
function showToast(message, type = 'success', duration = 3000) {
    // Create toast container if it doesn't exist
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(toastContainer);
    }
    
    // Create toast element
    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-white bg-${type}`;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');
    
    // Toast content
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    // Add toast to container
    toastContainer.appendChild(toastEl);
    
    // Initialize and show toast
    const toast = new bootstrap.Toast(toastEl, {
        autohide: true,
        delay: duration
    });
    toast.show();
    
    // Remove from DOM after hiding
    toastEl.addEventListener('hidden.bs.toast', function() {
        toastEl.remove();
    });
}

// Confirmation dialog helper
function confirmAction(message, callback) {
    if (window.confirm(message)) {
        callback();
    }
}
