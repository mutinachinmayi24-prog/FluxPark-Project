document.addEventListener('DOMContentLoaded', function () {
  // ------------------------------------------------------------------
  // Copy-to-clipboard buttons (invite links)
  // ------------------------------------------------------------------
  document.querySelectorAll('[data-copy-target]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var el = document.getElementById(btn.getAttribute('data-copy-target'));
      if (!el) return;
      var text = el.innerText || el.value;
      navigator.clipboard.writeText(text.trim()).then(function () {
        var original = btn.innerHTML;
        btn.innerHTML = '<i class="bi bi-check2"></i> Copied!';
        setTimeout(function () { btn.innerHTML = original; }, 1500);
      });
    });
  });

  // ------------------------------------------------------------------
  // Signup: toggle email / phone input
  // ------------------------------------------------------------------
  var emailRadio = document.getElementById('contact_type_email');
  var phoneRadio = document.getElementById('contact_type_phone');
  var contactInput = document.getElementById('contact');

  if (emailRadio && phoneRadio && contactInput) {
    var updateContactInput = function () {
      if (phoneRadio.checked) {
        contactInput.type = 'tel';
        contactInput.placeholder = '10-digit mobile number';
        contactInput.setAttribute('pattern', '[6-9][0-9]{9}');
        contactInput.setAttribute('maxlength', '10');
        contactInput.setAttribute('inputmode', 'numeric');
      } else {
        contactInput.type = 'email';
        contactInput.placeholder = 'you@example.com';
        contactInput.removeAttribute('pattern');
        contactInput.removeAttribute('maxlength');
        contactInput.removeAttribute('inputmode');
      }
    };
    emailRadio.addEventListener('change', updateContactInput);
    phoneRadio.addEventListener('change', updateContactInput);
    updateContactInput();
  }

  // ------------------------------------------------------------------
  // OTP input: digits only, auto-focus
  // ------------------------------------------------------------------
  var otpInput = document.getElementById('otp-code');
  if (otpInput) {
    otpInput.addEventListener('input', function () {
      otpInput.value = otpInput.value.replace(/\D/g, '').slice(0, 6);
    });
    otpInput.focus();
  }

  // ------------------------------------------------------------------
  // Generic dynamic table (vehicles, companies): add / remove rows
  // ------------------------------------------------------------------
  document.querySelectorAll('.dynamic-table').forEach(function (table) {
    var tbody = table.querySelector('tbody');
    var addBtn = document.querySelector('[data-add-row="' + table.id + '"]');

    var renumber = function () {
      tbody.querySelectorAll('tr').forEach(function (row, idx) {
        var cell = row.querySelector('.s-no');
        if (cell) cell.textContent = idx + 1;
      });
    };

    var addRow = function () {
      var firstRow = tbody.querySelector('tr');
      var newRow = firstRow.cloneNode(true);
      newRow.querySelectorAll('input, select').forEach(function (field) {
        field.value = '';
      });
      tbody.appendChild(newRow);
      renumber();
    };

    if (addBtn) {
      addBtn.addEventListener('click', addRow);
    }

    tbody.addEventListener('click', function (e) {
      var btn = e.target.closest('.remove-row');
      if (!btn) return;
      if (tbody.querySelectorAll('tr').length > 1) {
        btn.closest('tr').remove();
        renumber();
      }
    });

    table.addRow = addRow;
  });

  // ------------------------------------------------------------------
  // Office form: "Number of companies" auto-generates table rows
  // ------------------------------------------------------------------
  var numCompaniesInput = document.getElementById('num_companies');
  var companyTable = document.getElementById('company-table');
  if (numCompaniesInput && companyTable) {
    var companyTbody = companyTable.querySelector('tbody');
    numCompaniesInput.addEventListener('change', function () {
      var target = parseInt(numCompaniesInput.value, 10) || 0;
      var current = companyTbody.querySelectorAll('tr').length;
      while (current < target) {
        companyTable.addRow();
        current++;
      }
      while (current > target && current > 1) {
        companyTbody.lastElementChild.remove();
        current--;
      }
    });
  }

  // ------------------------------------------------------------------
  // Employee / Manager: Cab vs Self-transport toggle
  // ------------------------------------------------------------------
  var transportCab = document.getElementById('transport_cab');
  var transportSelf = document.getElementById('transport_self');
  var selfFields = document.getElementById('self-transport-fields');

  if (transportCab && transportSelf && selfFields) {
    var updateTransportFields = function () {
      var isSelf = transportSelf.checked;
      selfFields.classList.toggle('d-none', !isSelf);
      selfFields.querySelectorAll('input, select').forEach(function (field) {
        field.required = isSelf;
      });
    };
    transportCab.addEventListener('change', updateTransportFields);
    transportSelf.addEventListener('change', updateTransportFields);
    updateTransportFields();
  }
});
