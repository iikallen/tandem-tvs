import { useEffect, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, cursorFromUrl, type NewsFilters } from "../../shared/api";
import { Badge } from "../../shared/ui/Badge";
import { Card } from "../../shared/ui/Card";
import { SearchIcon } from "../../shared/ui/icons";
import { PageState } from "../../shared/ui/PageState";

export function NewsPage() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [unread, setUnread] = useState(false);
  const [category, setCategory] = useState("");
  const [author, setAuthor] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const filters: NewsFilters = {
    q: query,
    unread,
    category,
    author,
    date_from: dateFrom,
    date_to: dateTo,
  };
  const news = useInfiniteQuery({
    queryKey: ["news", filters],
    queryFn: ({ pageParam }) => api.news(filters, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => cursorFromUrl(page.next),
  });
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: api.categories,
  });
  const publications = news.data?.pages.flatMap((page) => page.results) ?? [];

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">Корпоративный портал</p>
          <h1>Новости</h1>
          <p className="page-description">Публикации, адресованные вам.</p>
        </div>
      </header>
      <section className="news-filters" aria-label="Фильтры новостей">
        <label className="search-field">
          <span className="sr-only">Поиск новостей</span>
          <SearchIcon />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Поиск по заголовку и тексту"
          />
        </label>
        <div className="segmented" aria-label="Статус прочтения">
          <button
            className={!unread ? "is-active" : ""}
            onClick={() => setUnread(false)}
          >
            Все
          </button>
          <button
            className={unread ? "is-active" : ""}
            onClick={() => setUnread(true)}
          >
            Непрочитанные
          </button>
        </div>
        <div className="filter-grid">
          <label>
            Категория
            <select
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="">Все категории</option>
              {categories.data?.map((item) => (
                <option key={item.slug} value={item.slug}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Автор
            <input
              value={author}
              onChange={(event) => setAuthor(event.target.value)}
              placeholder="Portal ID"
            />
          </label>
          <label>
            С даты
            <input
              type="date"
              value={dateFrom}
              onChange={(event) => setDateFrom(event.target.value)}
            />
          </label>
          <label>
            По дату
            <input
              type="date"
              value={dateTo}
              onChange={(event) => setDateTo(event.target.value)}
            />
          </label>
        </div>
      </section>
      {news.isPending ? (
        <PageState kind="loading" />
      ) : news.isError ? (
        <PageState error={news.error} />
      ) : publications.length === 0 ? (
        <div className="state">
          <div className="state__content">
            <h2>
              {query
                ? "Ничего не найдено"
                : unread
                  ? "Всё прочитано"
                  : "Новостей пока нет"}
            </h2>
            <p>Измените фильтры или вернитесь позже.</p>
          </div>
        </div>
      ) : (
        <div className="news-list">
          {publications.map((publication) => (
            <Link to={`/news/${publication.id}`} key={publication.id}>
              <Card
                className={`news-card ${publication.is_read ? "" : "is-unread"}`}
              >
                <div className="news-card__topline">
                  <Badge>{publication.category.name}</Badge>
                  {!publication.is_read && (
                    <span className="unread-dot">Новое</span>
                  )}
                </div>
                <h2>{publication.title}</h2>
                <p>{publication.summary}</p>
                <footer>
                  <span>{publication.author.full_name}</span>
                  <time dateTime={publication.published_at}>
                    {new Date(publication.published_at).toLocaleDateString(
                      "ru-RU",
                    )}
                  </time>
                  <span>{publication.view_count} просмотров</span>
                </footer>
              </Card>
            </Link>
          ))}
          {news.hasNextPage && (
            <button
              className="button button--secondary load-more"
              disabled={news.isFetchingNextPage}
              onClick={() => news.fetchNextPage()}
            >
              {news.isFetchingNextPage ? "Загружаем…" : "Показать ещё"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
