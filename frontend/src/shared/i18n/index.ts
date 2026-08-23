const ru = {
  appName: "Tandem Portal",
  stage: "Этап 1 · Основа и стык с порталом",
  home: "Главная",
  employees: "Сотрудники",
  profile: "Профиль",
  greeting: "Здравствуйте, {name}",
  homeDescription:
    "Ваш профиль и доступ синхронизированы с корпоративным порталом.",
  ssoConnected: "SSO подключён",
  contactDetails: "Контактные данные",
  organization: "Организация",
  department: "Подразделение",
  unitType: "Тип подразделения",
  email: "Электронная почта",
  phone: "Телефон",
  roles: "Роли в модуле",
  portalId: "ID в портале",
  position: "Должность",
  notSpecified: "Не указано",
  noOrganization: "Подразделение не назначено",
  employeeDirectory: "Справочник сотрудников",
  employeeDirectoryDescription:
    "Данные поступают из корпоративного портала и доступны только для чтения.",
  searchEmployees: "Поиск по имени, почте или должности",
  search: "Поиск",
  clearSearch: "Очистить поиск",
  loading: "Загружаем данные портала",
  loadingDescription: "Это займёт несколько секунд.",
  unauthorized: "Сессия портала не найдена",
  unauthorizedDescription:
    "Откройте модуль из корпоративного портала и попробуйте снова.",
  blocked: "Доступ заблокирован",
  blockedDescription:
    "Ваша учётная запись заблокирована в корпоративном портале.",
  unavailable: "Портал временно недоступен",
  unavailableDescription:
    "Не удалось проверить профиль. Повторите попытку позже.",
  error: "Не удалось загрузить данные",
  errorDescription: "Обновите страницу или повторите попытку позже.",
  emptyEmployees: "Сотрудники не найдены",
  emptyEmployeesDescription: "Измените поисковый запрос или очистите поле.",
  themeLight: "Включить светлую тему",
  themeDark: "Включить тёмную тему",
  navigation: "Основная навигация",
  mobileNavigation: "Мобильная навигация",
  employeeCount: "Найдено: {count}",
  roleEmployee: "Сотрудник",
  roleAuthor: "Автор",
  roleEditor: "Редактор",
  roleAdmin: "Администратор",
  kindCompany: "Компания",
  kindDepartment: "Департамент",
  kindTeam: "Команда",
} as const;

export type TranslationKey = keyof typeof ru;

export function t(
  key: TranslationKey,
  variables: Record<string, string | number> = {},
): string {
  let message: string = ru[key];
  for (const [name, value] of Object.entries(variables)) {
    message = message.replace(`{${name}}`, String(value));
  }
  return message;
}

export function roleLabel(role: string): string {
  const labels: Record<string, TranslationKey> = {
    employee: "roleEmployee",
    author: "roleAuthor",
    editor: "roleEditor",
    admin: "roleAdmin",
  };
  return labels[role] ? t(labels[role]) : role;
}

export function unitKindLabel(kind: string): string {
  const labels: Record<string, TranslationKey> = {
    company: "kindCompany",
    department: "kindDepartment",
    team: "kindTeam",
  };
  return labels[kind] ? t(labels[kind]) : kind;
}
